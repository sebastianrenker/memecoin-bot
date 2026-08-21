"""Protective memecoin rug/scam filters (a RISK filter, not a profit filter).

Heuristics grounded in how Solana memecoin rugs actually work (mint/freeze
authority still live, unlocked LP, extreme holder concentration, honeypot /
cannot-sell, insider bundling, dead volume, brand-new domain). Sources are
documented in RECHERCHE_MEMECOIN.md.

Passing these filters does NOT make a token safe or profitable — roughly the
vast majority of new Solana tokens show pump/rug warning signs. It only removes
some of the most obvious ways to lose everything instantly.

Design: ``apply_filters`` is PURE and unit-tested. Unknown metadata fields are
NEVER treated as pass or fail — we only reject on what we actually know (honest
degradation). Live fetchers (RugCheck / GoPlus / DexScreener) are best-effort
and return None on any failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TokenMetadata:
    symbol: str
    mint: Optional[str] = None
    # Market structure
    liquidity_usd: Optional[float] = None
    age_days: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    holders: Optional[int] = None
    unique_buyers_24h: Optional[int] = None
    # Concentration
    top_holder_pct: Optional[float] = None      # largest single holder, 0..1
    top10_holder_pct: Optional[float] = None     # sum of top-10, 0..1
    insiders_pct: Optional[float] = None         # bundled/insider supply, 0..1
    # Authorities / liquidity safety
    mint_authority_active: Optional[bool] = None     # can print more supply -> bad
    freeze_authority_active: Optional[bool] = None    # can freeze your wallet -> bad
    lp_locked_or_burned: Optional[bool] = None        # LP locked/burned -> good
    honeypot: Optional[bool] = None                   # cannot sell -> fatal
    # Aggregated third-party risk
    rugcheck_score: Optional[float] = None       # RugCheck normalized 0..100 (higher=riskier)
    risk_flags: List[str] = field(default_factory=list)
    source: str = ""


@dataclass
class FilterConfig:
    # Market structure
    min_liquidity_usd: float = 20_000.0
    min_age_days: float = 3.0
    min_volume_usd: float = 30_000.0
    min_holders: int = 150
    min_unique_buyers_24h: int = 75
    # Concentration
    max_top_holder_pct: float = 0.20
    max_top10_holder_pct: float = 0.50
    max_insiders_pct: float = 0.30
    # Authorities / liquidity safety (hard requirements when known)
    require_mint_authority_renounced: bool = True
    require_freeze_authority_disabled: bool = True
    require_lp_locked_or_burned: bool = True
    reject_honeypot: bool = True
    # Aggregated third-party risk
    max_rugcheck_score: Optional[float] = 40.0   # None disables


@dataclass
class FilterVerdict:
    passed: bool
    reasons: List[str]
    checked: int          # how many dimensions we actually had data for
    def as_dict(self) -> dict:
        return {"passed": self.passed, "reasons": self.reasons, "checked": self.checked}


def apply_filters(meta: TokenMetadata, cfg: FilterConfig) -> FilterVerdict:
    reasons: List[str] = []
    checked = 0

    def known(v) -> bool:
        return v is not None

    if known(meta.liquidity_usd):
        checked += 1
        if meta.liquidity_usd < cfg.min_liquidity_usd:
            reasons.append(f"liquidity ${meta.liquidity_usd:,.0f} < ${cfg.min_liquidity_usd:,.0f}")
    if known(meta.age_days):
        checked += 1
        if meta.age_days < cfg.min_age_days:
            reasons.append(f"age {meta.age_days:.1f}d < {cfg.min_age_days}d (fresh-launch rug risk)")
    if known(meta.volume_24h_usd):
        checked += 1
        if meta.volume_24h_usd < cfg.min_volume_usd:
            reasons.append(f"24h volume ${meta.volume_24h_usd:,.0f} < ${cfg.min_volume_usd:,.0f}")
    if known(meta.holders):
        checked += 1
        if meta.holders < cfg.min_holders:
            reasons.append(f"holders {meta.holders} < {cfg.min_holders}")
    if known(meta.unique_buyers_24h):
        checked += 1
        if meta.unique_buyers_24h < cfg.min_unique_buyers_24h:
            reasons.append(f"unique buyers {meta.unique_buyers_24h} < {cfg.min_unique_buyers_24h} (possible wash trading)")

    if known(meta.top_holder_pct):
        checked += 1
        if meta.top_holder_pct > cfg.max_top_holder_pct:
            reasons.append(f"top holder {meta.top_holder_pct:.0%} > {cfg.max_top_holder_pct:.0%}")
    if known(meta.top10_holder_pct):
        checked += 1
        if meta.top10_holder_pct > cfg.max_top10_holder_pct:
            reasons.append(f"top-10 holders {meta.top10_holder_pct:.0%} > {cfg.max_top10_holder_pct:.0%}")
    if known(meta.insiders_pct):
        checked += 1
        if meta.insiders_pct > cfg.max_insiders_pct:
            reasons.append(f"insider/bundled supply {meta.insiders_pct:.0%} > {cfg.max_insiders_pct:.0%}")

    if cfg.reject_honeypot and known(meta.honeypot):
        checked += 1
        if meta.honeypot:
            reasons.append("HONEYPOT: token cannot be sold (fatal)")
    if cfg.require_mint_authority_renounced and known(meta.mint_authority_active):
        checked += 1
        if meta.mint_authority_active:
            reasons.append("mint authority still active (owner can print & dump)")
    if cfg.require_freeze_authority_disabled and known(meta.freeze_authority_active):
        checked += 1
        if meta.freeze_authority_active:
            reasons.append("freeze authority active (owner can freeze your wallet)")
    if cfg.require_lp_locked_or_burned and known(meta.lp_locked_or_burned):
        checked += 1
        if not meta.lp_locked_or_burned:
            reasons.append("LP not locked/burned (dev can pull liquidity)")

    if cfg.max_rugcheck_score is not None and known(meta.rugcheck_score):
        checked += 1
        if meta.rugcheck_score > cfg.max_rugcheck_score:
            reasons.append(f"RugCheck risk score {meta.rugcheck_score:.0f} > {cfg.max_rugcheck_score:.0f}")

    return FilterVerdict(passed=len(reasons) == 0, reasons=reasons, checked=checked)


# --------------------------------------------------------------------------
# Live, best-effort metadata fetchers (network). Never raise; return None.
# --------------------------------------------------------------------------
def fetch_rugcheck(mint: str, timeout: float = 15.0, api_key: Optional[str] = None) -> Optional[TokenMetadata]:
    """Fetch a RugCheck report for a Solana mint. Public endpoint; degrades to None.

    RugCheck's JSON shape can change; we parse defensively. Docs:
    https://api.rugcheck.xyz/swagger/index.html
    """
    try:
        import requests
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
        headers = {"accept": "application/json"}
        if api_key:
            headers["X-API-KEY"] = api_key
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code != 200:
            return None
        d = r.json() or {}
        risks = [x.get("name", "") for x in (d.get("risks") or []) if isinstance(x, dict)]
        top = d.get("topHolders") or []
        top_pct = None
        top10_pct = None
        if top:
            def _pct(h):
                p = h.get("pct")
                return (float(p) / 100.0) if p is not None else None
            first = _pct(top[0]) if top else None
            top_pct = first
            vals = [(_pct(h) or 0.0) for h in top[:10]]
            top10_pct = sum(vals) if vals else None
        mint_auth = d.get("mintAuthority")
        freeze_auth = d.get("freezeAuthority")
        lockers = d.get("lockers") or d.get("markets") or []
        lp_locked = None
        if isinstance(d.get("lockerOwners"), dict) and d.get("lockerOwners"):
            lp_locked = True
        return TokenMetadata(
            symbol=(d.get("tokenMeta") or {}).get("symbol") or mint[:6],
            mint=mint,
            top_holder_pct=top_pct,
            top10_holder_pct=top10_pct,
            insiders_pct=(float(d["insidersPct"]) / 100.0 if d.get("insidersPct") is not None else None),
            mint_authority_active=(mint_auth is not None and mint_auth != ""),
            freeze_authority_active=(freeze_auth is not None and freeze_auth != ""),
            lp_locked_or_burned=lp_locked,
            rugcheck_score=(float(d["score"]) if d.get("score") is not None else None),
            risk_flags=[x for x in risks if x],
            source="rugcheck",
        )
    except Exception:
        return None


def fetch_goplus_solana(mint: str, timeout: float = 15.0) -> Optional[TokenMetadata]:
    """GoPlus Solana token security (best-effort). Complements RugCheck."""
    try:
        import requests
        url = f"https://api.gopluslabs.io/api/v1/solana/token_security?contract_addresses={mint}"
        r = requests.get(url, headers={"accept": "application/json"}, timeout=timeout)
        if r.status_code != 200:
            return None
        res = ((r.json() or {}).get("result") or {}).get(mint) or {}
        if not res:
            return None
        def _b(x):
            return None if x is None else str(x) in ("1", "true", "True")
        return TokenMetadata(
            symbol=res.get("token_symbol") or mint[:6], mint=mint,
            mint_authority_active=_b(res.get("mintable", {}).get("status") if isinstance(res.get("mintable"), dict) else res.get("mintable")),
            freeze_authority_active=_b(res.get("freezable", {}).get("status") if isinstance(res.get("freezable"), dict) else res.get("freezable")),
            honeypot=_b(res.get("non_transferable")),
            holders=(int(res["holder_count"]) if res.get("holder_count") not in (None, "") else None),
            source="goplus",
        )
    except Exception:
        return None


def merge_metadata(*metas: Optional[TokenMetadata]) -> Optional[TokenMetadata]:
    """Combine partial metadata from several sources; first non-None wins per field."""
    present = [m for m in metas if m is not None]
    if not present:
        return None
    out = TokenMetadata(symbol=present[0].symbol, mint=present[0].mint)
    fields = [f for f in vars(out) if f not in ("symbol", "mint", "risk_flags", "source")]
    for m in present:
        for f in fields:
            if getattr(out, f) is None and getattr(m, f) is not None:
                setattr(out, f, getattr(m, f))
        out.risk_flags = list({*out.risk_flags, *m.risk_flags})
    out.source = "+".join(sorted({m.source for m in present if m.source}))
    return out

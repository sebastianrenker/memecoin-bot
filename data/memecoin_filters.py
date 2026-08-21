"""Protective pre-trade memecoin filters (a RISK filter, not a profit filter).

These heuristics try to avoid the worst structural traps — dust liquidity,
brand-new listings, no volume, extreme holder concentration (a rug heuristic).
Passing them does NOT make a token safe or profitable; it only removes some of
the most obvious ways to lose everything instantly.

The core ``apply_filters`` function is pure and testable. Fetching live metadata
from DexScreener is separate and best-effort.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TokenMetadata:
    symbol: str
    liquidity_usd: Optional[float] = None
    age_days: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    top10_holder_pct: Optional[float] = None   # 0..1


@dataclass
class FilterConfig:
    min_liquidity_usd: float = 50_000.0
    min_age_days: float = 30.0
    min_volume_usd: float = 100_000.0
    max_top10_holder_pct: float = 0.6


@dataclass
class FilterVerdict:
    passed: bool
    reasons: List[str]


def apply_filters(meta: TokenMetadata, cfg: FilterConfig) -> FilterVerdict:
    reasons: List[str] = []
    if meta.liquidity_usd is not None and meta.liquidity_usd < cfg.min_liquidity_usd:
        reasons.append(f"liquidity ${meta.liquidity_usd:,.0f} < ${cfg.min_liquidity_usd:,.0f}")
    if meta.age_days is not None and meta.age_days < cfg.min_age_days:
        reasons.append(f"age {meta.age_days:.1f}d < {cfg.min_age_days}d (fresh-listing rug risk)")
    if meta.volume_24h_usd is not None and meta.volume_24h_usd < cfg.min_volume_usd:
        reasons.append(f"24h volume ${meta.volume_24h_usd:,.0f} < ${cfg.min_volume_usd:,.0f}")
    if meta.top10_holder_pct is not None and meta.top10_holder_pct > cfg.max_top10_holder_pct:
        reasons.append(f"top-10 holders {meta.top10_holder_pct:.0%} > {cfg.max_top10_holder_pct:.0%} (rug heuristic)")
    return FilterVerdict(passed=len(reasons) == 0, reasons=reasons)


def fetch_dexscreener_metadata(query: str, timeout: float = 20.0) -> Optional[TokenMetadata]:
    """Best-effort metadata from DexScreener. Returns None on any failure.

    ``query`` is a token address or symbol search. Uses the highest-liquidity
    pair found. Never raises — filters degrade to 'unknown' fields.
    """
    try:
        import time as _t

        import requests
        url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
        r = requests.get(url, timeout=timeout, headers={"accept": "application/json"})
        if r.status_code != 200:
            return None
        pairs = (r.json() or {}).get("pairs") or []
        if not pairs:
            return None
        pairs.sort(key=lambda p: (p.get("liquidity", {}) or {}).get("usd", 0) or 0, reverse=True)
        p = pairs[0]
        liq = (p.get("liquidity", {}) or {}).get("usd")
        vol = (p.get("volume", {}) or {}).get("h24")
        created_ms = p.get("pairCreatedAt")
        age_days = None
        if created_ms:
            age_days = max(0.0, (_t.time() * 1000 - float(created_ms)) / 86_400_000.0)
        return TokenMetadata(
            symbol=query,
            liquidity_usd=float(liq) if liq is not None else None,
            age_days=age_days,
            volume_24h_usd=float(vol) if vol is not None else None,
            top10_holder_pct=None,  # not available from DexScreener
        )
    except Exception:
        return None

"""Neutral attention / risk signals and watchlist building.

IMPORTANT HONESTY BOUNDARY: an "attention score" describes how much *current*
on-chain and social activity a token has RIGHT NOW. It is explicitly **not** a
prediction that the price will go up. As the traders themselves say: by the time
a coin is trending on Twitter you are usually too late, and the vast majority of
new tokens are pumps or rugs. This module ranks *attention*, pairs it with the
rug-filter verdict, and hands you links to VERIFY on Axiom/GMGN/RugCheck — it
does not tell you what will "explode".

The scoring function is pure and unit-tested. The DexScreener fetchers are
best-effort (public API, no key) and return [] on failure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from data.memecoin_filters import (FilterConfig, FilterVerdict, TokenMetadata,
                                    apply_filters)


@dataclass
class TokenFeatures:
    symbol: str
    mint: str
    chain: str = "solana"
    liquidity_usd: float = 0.0
    volume_24h_usd: float = 0.0
    volume_5m_usd: float = 0.0
    price_change_1h: float = 0.0      # percent
    buys_5m: int = 0
    sells_5m: int = 0
    boosts: int = 0
    has_socials: bool = False
    age_hours: float = 0.0
    pair_url: str = ""
    pool_address: str = ""      # AMM pool address (for on-chain OHLCV via GeckoTerminal)
    price_usd: float = 0.0
    price_change_24h: float = 0.0
    price_change_6h: float = 0.0
    fdv: float = 0.0
    market_cap: float = 0.0
    dex: str = ""
    feed: str = ""              # which live feed it came from: new|trending|top|boosted
    socials: dict = field(default_factory=dict)   # {twitter,telegram,website}


@dataclass
class TokenSignal:
    symbol: str
    mint: str
    chain: str
    attention: float                 # 0..100, descriptive of CURRENT activity only
    tradeable: bool                  # passed the rug filters
    risk: FilterVerdict
    features: Dict
    links: Dict[str, str]
    note: str = ("Attention is a snapshot of current activity, NOT a price "
                 "prediction. Most memecoins go to zero. Verify every token on "
                 "RugCheck/GMGN before ever risking real money.")

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "mint": self.mint, "chain": self.chain,
                "attention": self.attention, "tradeable": self.tradeable,
                "risk": self.risk.as_dict(), "features": self.features,
                "links": self.links, "note": self.note}


def _log_norm(x: float, full: float) -> float:
    """Map x>=0 to 0..1 via log scale, reaching ~1 near ``full``."""
    if x <= 0 or full <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log1p(x) / math.log1p(full)))


def attention_score(f: TokenFeatures) -> float:
    """Descriptive 0..100 attention score. NOT predictive."""
    vol = _log_norm(f.volume_24h_usd, 5_000_000)          # activity magnitude
    liq = _log_norm(f.liquidity_usd, 500_000)             # depth (also a floor)
    recent = _log_norm(f.volume_5m_usd * 288, 5_000_000)  # annualise 5m to ~24h pace
    total_tx = f.buys_5m + f.sells_5m
    buy_press = (f.buys_5m / total_tx) if total_tx > 0 else 0.5
    tx = _log_norm(total_tx, 500)
    extras = 0.0
    extras += 0.5 if f.has_socials else 0.0
    extras += min(1.0, f.boosts / 50.0)
    extras = min(1.0, extras)

    score = (0.30 * vol + 0.15 * liq + 0.25 * recent + 0.15 * tx +
             0.10 * buy_press + 0.05 * extras) * 100.0
    return round(max(0.0, min(100.0, score)), 1)


def _x_search(symbol: str, mint: str) -> str:
    """Link to the LIVE X/Twitter feed for the coin (honest alternative to a
    paid sentiment API): cashtag search when the symbol is clean, else mint."""
    import urllib.parse as _u
    if symbol and symbol.replace("_", "").isalnum() and len(symbol) <= 12:
        q = f"${symbol}"
    else:
        q = mint
    return "https://x.com/search?q=" + _u.quote(q) + "&f=live"


def token_links(mint: str, chain: str = "solana", pair_url: str = "",
                symbol: str = "", socials: Optional[dict] = None) -> Dict[str, str]:
    socials = socials or {}
    links = {
        "dexscreener": pair_url or f"https://dexscreener.com/{chain}/{mint}",
        "rugcheck": f"https://rugcheck.xyz/tokens/{mint}",
        "gmgn": f"https://gmgn.ai/{'sol' if chain == 'solana' else chain}/token/{mint}",
        "axiom": f"https://axiom.trade/t/{mint}",       # OBSERVE only (Axiom is a live venue)
        "birdeye": f"https://birdeye.so/token/{mint}?chain={chain}",
        "x_search": _x_search(symbol, mint),            # LIVE Twitter/X feed for the coin
    }
    if socials.get("twitter"):
        links["x_official"] = socials["twitter"]
    if socials.get("telegram"):
        links["telegram"] = socials["telegram"]
    if socials.get("website"):
        links["website"] = socials["website"]
    return links


def build_signal(f: TokenFeatures, meta: Optional[TokenMetadata],
                 cfg: Optional[FilterConfig] = None) -> TokenSignal:
    cfg = cfg or FilterConfig()
    # Ensure basic market-structure fields flow into the rug filter even without RugCheck.
    m = meta or TokenMetadata(symbol=f.symbol, mint=f.mint)
    if m.liquidity_usd is None:
        m.liquidity_usd = f.liquidity_usd
    if m.volume_24h_usd is None:
        m.volume_24h_usd = f.volume_24h_usd
    if m.age_days is None and f.age_hours:
        m.age_days = f.age_hours / 24.0
    verdict = apply_filters(m, cfg)
    return TokenSignal(
        symbol=f.symbol, mint=f.mint, chain=f.chain,
        attention=attention_score(f), tradeable=verdict.passed, risk=verdict,
        features={"liquidity_usd": f.liquidity_usd, "volume_24h_usd": f.volume_24h_usd,
                  "volume_5m_usd": f.volume_5m_usd, "price_change_1h": f.price_change_1h,
                  "price_change_6h": f.price_change_6h, "price_change_24h": f.price_change_24h,
                  "price_usd": f.price_usd, "fdv": f.fdv, "market_cap": f.market_cap,
                  "buys_5m": f.buys_5m, "sells_5m": f.sells_5m, "boosts": f.boosts,
                  "has_socials": f.has_socials, "age_hours": round(f.age_hours, 1),
                  "dex": f.dex, "feed": f.feed, "pool_address": f.pool_address},
        links=token_links(f.mint, f.chain, f.pair_url, f.symbol, f.socials))


def build_watchlist(features: List[TokenFeatures], metas: Dict[str, Optional[TokenMetadata]],
                    cfg: Optional[FilterConfig] = None,
                    tradeable_only: bool = False) -> List[TokenSignal]:
    signals = [build_signal(f, metas.get(f.mint), cfg) for f in features]
    if tradeable_only:
        signals = [s for s in signals if s.tradeable]
    signals.sort(key=lambda s: s.attention, reverse=True)
    return signals


# --------------------------------------------------------------------------
# Best-effort DexScreener fetchers (public, no key). Never raise; return [].
# --------------------------------------------------------------------------
def _get_json(url: str, timeout: float = 15.0, retries: int = 3):
    import time as _t

    import requests
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"accept": "application/json"}, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429 and attempt < retries - 1:
                _t.sleep(2.0 * (attempt + 1))   # rate-limited: back off and retry
                continue
            return None
        except Exception:
            if attempt < retries - 1:
                _t.sleep(1.0 * (attempt + 1))
                continue
            return None
    return None


def _extract_socials(info: dict) -> dict:
    out = {}
    for s in (info.get("socials") or []):
        t = (s.get("type") or "").lower()
        if t in ("twitter", "x") and s.get("url"):
            out["twitter"] = s["url"]
        elif t == "telegram" and s.get("url"):
            out["telegram"] = s["url"]
    sites = info.get("websites") or []
    if sites:
        first = sites[0]
        out["website"] = first.get("url") if isinstance(first, dict) else first
    return out


def _features_from_pair(p: dict) -> Optional[TokenFeatures]:
    try:
        base = p.get("baseToken") or {}
        vol = p.get("volume") or {}
        pc = p.get("priceChange") or {}
        txns = p.get("txns") or {}
        m5 = txns.get("m5") or {}
        info = p.get("info") or {}
        created = p.get("pairCreatedAt")
        age_h = 0.0
        if created:
            import time as _t
            age_h = max(0.0, (_t.time() * 1000 - float(created)) / 3_600_000.0)
        return TokenFeatures(
            symbol=base.get("symbol") or "?", mint=base.get("address") or "",
            chain=p.get("chainId") or "solana",
            liquidity_usd=float((p.get("liquidity") or {}).get("usd") or 0.0),
            volume_24h_usd=float(vol.get("h24") or 0.0),
            volume_5m_usd=float(vol.get("m5") or 0.0),
            price_change_1h=float(pc.get("h1") or 0.0),
            price_change_6h=float(pc.get("h6") or 0.0),
            price_change_24h=float(pc.get("h24") or 0.0),
            price_usd=float(p.get("priceUsd") or 0.0),
            fdv=float(p.get("fdv") or 0.0),
            market_cap=float(p.get("marketCap") or 0.0),
            dex=p.get("dexId") or "",
            buys_5m=int(m5.get("buys") or 0), sells_5m=int(m5.get("sells") or 0),
            boosts=int((p.get("boosts") or {}).get("active") or 0),
            has_socials=bool(info.get("socials")),
            socials=_extract_socials(info),
            age_hours=age_h, pair_url=p.get("url") or "",
            pool_address=p.get("pairAddress") or "")
    except Exception:
        return None


# Short chain aliases -> DexScreener chainIds.
CHAIN_ALIASES = {"sol": "solana", "solana": "solana", "bnb": "bsc", "bsc": "bsc",
                 "eth": "ethereum", "ethereum": "ethereum", "base": "base"}


def _norm_chains(chains) -> set:
    if isinstance(chains, str):
        chains = [c.strip() for c in chains.split(",") if c.strip()]
    return {CHAIN_ALIASES.get(c.lower(), c.lower()) for c in chains}


def fetch_dexscreener_boosted(chains="solana", limit: int = 30) -> List[TokenFeatures]:
    """Latest *boosted* tokens across one or more chains, enriched with pair
    stats. ``chains`` may be a comma string or list ("sol,bnb,eth"). Best-effort."""
    try:
        wanted = _norm_chains(chains)
        boosts = _get_json("https://api.dexscreener.com/token-boosts/latest/v1") or []
        seen = set()
        picks = []  # (chainId, mint)
        for b in boosts:
            cid = (b.get("chainId") or "").lower()
            addr = b.get("tokenAddress")
            if cid in wanted and addr and (cid, addr) not in seen:
                seen.add((cid, addr))
                picks.append((cid, addr))
        picks = picks[:limit]
        out: List[TokenFeatures] = []
        for cid, mint in picks:
            data = _get_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
            allp = (data or {}).get("pairs") or []
            pairs = [p for p in allp if (p.get("chainId") or "").lower() == cid] or allp
            if not pairs:
                continue
            pairs.sort(key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0, reverse=True)
            f = _features_from_pair(pairs[0])
            if f and f.mint:
                f.feed = "boosted"
                out.append(f)
        return out
    except Exception:
        return []


# GeckoTerminal network ids (differ from DexScreener: eth not ethereum).
GT_NETWORKS = {"sol": "solana", "solana": "solana", "bnb": "bsc", "bsc": "bsc",
               "eth": "eth", "ethereum": "eth", "base": "base"}
_GT = "https://api.geckoterminal.com/api/v2"


def _gt_pool_to_features(pool: dict, tokmap: dict, network: str, feed: str) -> Optional[TokenFeatures]:
    try:
        a = pool.get("attributes") or {}
        rel = pool.get("relationships") or {}
        base_id = ((rel.get("base_token") or {}).get("data") or {}).get("id") or ""
        tok = tokmap.get(base_id, {})
        mint = tok.get("address") or (base_id.split("_", 1)[-1] if "_" in base_id else base_id)
        vol = a.get("volume_usd") or {}
        pc = a.get("price_change_percentage") or {}
        tx = (a.get("transactions") or {}).get("m5") or {}
        created = a.get("pool_created_at")
        age_h = 0.0
        if created:
            import datetime as _dt
            try:
                dtv = _dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_h = max(0.0, (_dt.datetime.now(_dt.timezone.utc) - dtv).total_seconds() / 3600.0)
            except Exception:
                pass
        dex_id = ((rel.get("dex") or {}).get("data") or {}).get("id") or ""
        chain = {"solana": "solana", "bsc": "bsc", "eth": "ethereum", "base": "base"}.get(network, network)
        return TokenFeatures(
            symbol=tok.get("symbol") or (a.get("name") or "?").split(" ")[0],
            mint=mint, chain=chain,
            liquidity_usd=float(a.get("reserve_in_usd") or 0.0),
            volume_24h_usd=float(vol.get("h24") or 0.0),
            volume_5m_usd=float(vol.get("m5") or 0.0),
            price_change_1h=float(pc.get("h1") or 0.0),
            price_change_6h=float(pc.get("h6") or 0.0),
            price_change_24h=float(pc.get("h24") or 0.0),
            price_usd=float(a.get("base_token_price_usd") or 0.0),
            fdv=float(a.get("fdv_usd") or 0.0),
            market_cap=float(a.get("market_cap_usd") or 0.0),
            dex=dex_id, feed=feed,
            buys_5m=int(tx.get("buys") or 0), sells_5m=int(tx.get("sells") or 0),
            age_hours=age_h, pool_address=a.get("address") or "",
            pair_url=f"https://www.geckoterminal.com/{network}/pools/{a.get('address','')}")
    except Exception:
        return None


def _gt_fetch_feed(network: str, feed: str, pages: int) -> List[TokenFeatures]:
    ep = {"new": "new_pools", "trending": "trending_pools", "top": "pools"}[feed]
    out: List[TokenFeatures] = []
    for page in range(1, pages + 1):
        data = _get_json(f"{_GT}/networks/{network}/{ep}?include=base_token&page={page}")
        if not data:
            break
        tokmap = {t.get("id"): (t.get("attributes") or {})
                  for t in (data.get("included") or []) if t.get("type") == "token"}
        pools = data.get("data") or []
        if not pools:
            break
        for p in pools:
            f = _gt_pool_to_features(p, tokmap, network, feed)
            if f and f.mint:
                out.append(f)
    return out


def fetch_geckoterminal(chains="solana", feeds=("trending", "new", "top"),
                        pages: int = 1, limit: int = 300) -> List[TokenFeatures]:
    """Fetch MANY live coins across chains and feeds (new/trending/top pools).

    This is the 'see every coin' feed (public GeckoTerminal API, no key). Dedups
    by (chain, mint), keeping the first feed a coin appears in. Best-effort."""
    try:
        if isinstance(chains, str):
            chains = [c.strip() for c in chains.split(",") if c.strip()]
        if isinstance(feeds, str):
            feeds = [c.strip() for c in feeds.split(",") if c.strip()]
        seen = set()
        out: List[TokenFeatures] = []
        for c in chains:
            net = GT_NETWORKS.get(c.lower(), c.lower())
            for feed in feeds:
                for f in _gt_fetch_feed(net, feed, pages):
                    key = (f.chain, f.mint)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(f)
                    if len(out) >= limit:
                        return out
        return out
    except Exception:
        return []

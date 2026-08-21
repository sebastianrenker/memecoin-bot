"""Optional auto-discovery of top memecoins on a CEX by quote volume.

Applies a minimum-quote-volume filter and (best-effort) a minimum-age filter.
This is a RISK FILTER, not a profit filter: it just avoids the very thinnest and
freshest listings. It never guarantees anything about returns.

Memecoin identification on a CEX is heuristic (a curated keyword/known-symbol
set), because exchanges don't tag "memecoin". Be explicit about that limitation.
"""
from __future__ import annotations

from typing import List, Optional

# A conservative, well-known memecoin base-symbol set. Extend as needed.
KNOWN_MEME_BASES = {
    "DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "BOME", "MEME", "MEW",
    "POPCAT", "BRETT", "TURBO", "MOG", "PONKE", "DEGEN", "NEIRO", "GOAT",
    "PNUT", "ACT", "CHILLGUY", "MOODENG", "DOGS", "BABYDOGE",
}


def discover_memecoins(source, quote: str = "USDT", top_n: int = 20,
                       min_quote_volume: float = 5_000_000.0,
                       min_age_days: int = 30, timeframe: str = "1h",
                       meme_bases: Optional[set] = None) -> List[str]:
    """Return up to ``top_n`` symbols ranked by 24h quote volume.

    ``source`` must be a CcxtSource (exposes the underlying ccxt exchange).
    Failures degrade gracefully to an empty list — the caller falls back to the
    configured static universe.
    """
    meme_bases = meme_bases or KNOWN_MEME_BASES
    try:
        ex = source._exchange()
        ex.load_markets()
        tickers = ex.fetch_tickers()
    except Exception:
        return []

    candidates = []
    for sym, t in tickers.items():
        if not sym.endswith(f"/{quote}"):
            continue
        base = sym.split("/")[0]
        if base not in meme_bases:
            continue
        qv = t.get("quoteVolume") or 0.0
        if qv < min_quote_volume:
            continue
        candidates.append((sym, float(qv)))

    candidates.sort(key=lambda x: x[1], reverse=True)
    symbols = [s for s, _ in candidates[:top_n]]

    # Best-effort min-age filter using available history length.
    if min_age_days > 0 and symbols:
        aged = []
        for s in symbols:
            try:
                df = source.fetch_ohlcv(s, timeframe, min_age_days + 5)
                # need enough bars to plausibly span min_age_days
                from core.utils import timeframe_seconds
                span_days = len(df) * timeframe_seconds(timeframe) / 86400.0
                if span_days >= min_age_days:
                    aged.append(s)
            except Exception:
                continue
        return aged
    return symbols

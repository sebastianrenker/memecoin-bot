"""Build a configured DataSource from Settings (config reaches the class)."""
from __future__ import annotations

from config.settings import Settings
from data.cache import OHLCVCache


def build_cache(s: Settings) -> OHLCVCache:
    return OHLCVCache(cache_dir=s.get("data.cache_dir", ".cache"),
                      ttl_min=float(s.get("data.cache_ttl_min", 30)))


def build_data_source(s: Settings):
    src = str(s.get("data.source", "ccxt")).lower()
    cache = build_cache(s)
    retries = int(s.get("data.max_retries", 4))
    backoff = float(s.get("data.backoff_base_sec", 1.5))
    if src == "ccxt":
        from data.ccxt_source import CcxtSource
        return CcxtSource(exchange=s.get("data.exchange", "binance"), cache=cache,
                          max_retries=retries, backoff_base_sec=backoff)
    if src == "dex":
        from data.dex_source import DexSource
        return DexSource(cache=cache, max_retries=retries, backoff_base_sec=backoff)
    raise ValueError(f"unknown data.source: {src!r} (use 'ccxt' or 'dex')")

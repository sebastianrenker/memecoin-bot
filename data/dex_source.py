"""Optional on-chain DEX OHLCV via GeckoTerminal's public API.

HONEST CAVEAT: on-chain pool history is short, patchy and noisy. Many pools
return too few candles to validate a strategy — so a lot of DEX combinations
will (correctly) fail the data checks and be skipped. That is the intended,
truthful behaviour, not a bug.

Symbols for this source use the form ``"network:pool_address"``
(e.g. ``"solana:7xKX...."``). Still real data — never fabricated.
"""
from __future__ import annotations

import time
from typing import List, Optional

import pandas as pd

from data.base import DataSource, DataUnavailable, normalize_ohlcv

_GT_BASE = "https://api.geckoterminal.com/api/v2"
_TF_MAP = {  # GeckoTerminal uses {timeframe}/{aggregate}
    "1m": ("minute", 1), "5m": ("minute", 5), "15m": ("minute", 15),
    "1h": ("hour", 1), "4h": ("hour", 4), "12h": ("hour", 12), "1d": ("day", 1),
}


class DexSource(DataSource):
    name = "dex"

    def __init__(self, cache=None, max_retries: int = 4, backoff_base_sec: float = 1.5):
        self.cache = cache
        self.max_retries = max_retries
        self.backoff_base = backoff_base_sec

    def _get_json(self, url: str, params: dict):
        import requests
        last = None
        for attempt in range(self.max_retries):
            try:
                r = requests.get(url, params=params, timeout=20,
                                 headers={"accept": "application/json"})
                if r.status_code == 200:
                    return r.json()
                last = f"HTTP {r.status_code}"
            except Exception as e:
                last = e
            if attempt < self.max_retries - 1:
                time.sleep(self.backoff_base * (2 ** attempt))
        raise DataUnavailable(f"GeckoTerminal request failed: {last}")

    def fetch_ohlcv(self, symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        if ":" not in symbol:
            raise DataUnavailable(f"DEX symbol must be 'network:pool_address', got {symbol!r}")
        if timeframe not in _TF_MAP:
            raise DataUnavailable(f"DEX source does not support timeframe {timeframe}")
        network, pool = symbol.split(":", 1)

        cache_src = f"{self.name}_{lookback_days}d"
        if self.cache is not None:
            cached = self.cache.get(cache_src, symbol, timeframe)
            if cached is not None and not cached.empty:
                return cached

        tf, agg = _TF_MAP[timeframe]
        url = f"{_GT_BASE}/networks/{network}/pools/{pool}/ohlcv/{tf}"
        data = self._get_json(url, {"aggregate": agg, "limit": 1000, "currency": "usd"})
        try:
            arr = data["data"]["attributes"]["ohlcv_list"]
        except (KeyError, TypeError) as e:
            raise DataUnavailable(f"unexpected GeckoTerminal payload for {symbol}") from e
        if not arr:
            raise DataUnavailable(f"no on-chain OHLCV for {symbol} {timeframe}")

        # ohlcv_list rows: [ts_sec, open, high, low, close, volume]
        rows = [[int(r[0]) * 1000, r[1], r[2], r[3], r[4], r[5]] for r in arr]
        df = normalize_ohlcv(rows)
        if self.cache is not None:
            self.cache.put(cache_src, symbol, timeframe, df)
        return df

    def latest_price(self, symbol: str) -> Optional[float]:
        try:
            df = self.fetch_ohlcv(symbol, "1h", 2)
            return float(df["close"].iloc[-1])
        except Exception:
            return None

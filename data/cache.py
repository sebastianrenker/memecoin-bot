"""On-disk OHLCV cache (CSV, no extra deps) with a TTL.

Caching cuts redundant API calls (and rate-limit pain). A stale entry past the
TTL is ignored so live loops still refresh. Cached data is real data that was
previously fetched — the cache never invents candles.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import pandas as pd

from data.base import OHLCV_COLUMNS


class OHLCVCache:
    def __init__(self, cache_dir: str, ttl_min: float = 30.0):
        self.cache_dir = cache_dir
        self.ttl_sec = ttl_min * 60.0
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, source: str, symbol: str, timeframe: str) -> str:
        safe = symbol.replace("/", "_").replace(":", "_")
        return os.path.join(self.cache_dir, f"{source}__{safe}__{timeframe}.csv")

    def get(self, source: str, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        path = self._path(source, symbol, timeframe)
        if not os.path.exists(path):
            return None
        if (time.time() - os.path.getmtime(path)) > self.ttl_sec:
            return None
        try:
            df = pd.read_csv(path)
        except Exception:
            return None
        if not set(OHLCV_COLUMNS).issubset(df.columns) or df.empty:
            return None
        df["timestamp"] = df["timestamp"].astype("int64")
        return df.set_index("timestamp", drop=False)

    def put(self, source: str, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        path = self._path(source, symbol, timeframe)
        df[OHLCV_COLUMNS].to_csv(path, index=False)

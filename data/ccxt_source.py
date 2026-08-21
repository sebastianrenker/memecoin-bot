"""CEX OHLCV via ccxt — the primary, most-trustworthy memecoin data source.

Real candles only. On repeated failure we raise DataUnavailable so the caller
skips the combination (data.require_real). Includes retry with exponential
backoff and paginated fetching to cover the full lookback window.
"""
from __future__ import annotations

import time
from typing import List, Optional

import pandas as pd

from core.utils import timeframe_ms
from data.base import DataSource, DataUnavailable, normalize_ohlcv


class CcxtSource(DataSource):
    name = "ccxt"

    def __init__(self, exchange: str = "binance", cache=None, max_retries: int = 4,
                 backoff_base_sec: float = 1.5, enable_rate_limit: bool = True):
        self.exchange_id = exchange
        self.cache = cache
        self.max_retries = max_retries
        self.backoff_base = backoff_base_sec
        self._ex = None
        self._enable_rate_limit = enable_rate_limit

    def _exchange(self):
        if self._ex is None:
            try:
                import ccxt
            except ImportError as e:
                raise DataUnavailable("ccxt is not installed (pip install ccxt)") from e
            if not hasattr(ccxt, self.exchange_id):
                raise DataUnavailable(f"unknown ccxt exchange: {self.exchange_id}")
            self._ex = getattr(ccxt, self.exchange_id)({"enableRateLimit": self._enable_rate_limit})
        return self._ex

    def _retry(self, fn, what: str):
        last = None
        for attempt in range(self.max_retries):
            try:
                return fn()
            except Exception as e:  # network / rate-limit / exchange errors
                last = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_base * (2 ** attempt))
        raise DataUnavailable(f"{what} failed after {self.max_retries} tries: {last}")

    def fetch_ohlcv(self, symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        cache_src = f"{self.name}_{lookback_days}d"
        if self.cache is not None:
            cached = self.cache.get(cache_src, symbol, timeframe)
            if cached is not None and not cached.empty:
                return cached

        ex = self._exchange()
        tf_ms = timeframe_ms(timeframe)
        since = ex.milliseconds() - lookback_days * 86_400_000
        all_rows: List[list] = []
        cursor = since
        limit = 1000

        while True:
            batch = self._retry(
                lambda: ex.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit),
                f"fetch_ohlcv {symbol} {timeframe}")
            if not batch:
                break
            all_rows.extend(batch)
            last_ts = batch[-1][0]
            if len(batch) < limit or last_ts >= ex.milliseconds() - tf_ms:
                break
            cursor = last_ts + tf_ms
            if cursor > ex.milliseconds():
                break

        if not all_rows:
            raise DataUnavailable(f"no OHLCV returned for {symbol} {timeframe}")
        df = normalize_ohlcv(all_rows)
        if self.cache is not None:
            self.cache.put(cache_src, symbol, timeframe, df)
        return df

    def latest_price(self, symbol: str) -> Optional[float]:
        ex = self._exchange()
        t = self._retry(lambda: ex.fetch_ticker(symbol), f"fetch_ticker {symbol}")
        return float(t["last"]) if t and t.get("last") is not None else None

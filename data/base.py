"""Data source abstraction. All sources return REAL OHLCV or nothing.

Contract: ``fetch_ohlcv`` returns a DataFrame with columns
[timestamp, open, high, low, close, volume] (timestamp in UTC ms, ascending)
indexed by timestamp, or raises DataUnavailable. Callers running with
data.require_real=true must SKIP the combination on failure — never fabricate.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class DataUnavailable(RuntimeError):
    """Raised when real data cannot be fetched. Never substitute fake data."""


def normalize_ohlcv(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=OHLCV_COLUMNS)
    df = df.dropna()
    df["timestamp"] = df["timestamp"].astype("int64")
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df.index = df["timestamp"].values
    return df.reset_index(drop=True).set_index("timestamp", drop=False)


class DataSource(ABC):
    name: str = "base"

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        raise NotImplementedError

    def latest_price(self, symbol: str) -> Optional[float]:
        return None

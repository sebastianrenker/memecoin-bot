"""Timeframe helpers and the closed_bars() guard against look-ahead.

The single most important correctness rule in this project: signals and ATR are
computed only on *closed* candles. The currently-forming last bar (now <
open_time + timeframe) is dropped before any strategy sees the data.
"""
from __future__ import annotations

import time
from typing import Optional

import pandas as pd

_TF_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800,
}


def timeframe_seconds(tf: str) -> int:
    if tf not in _TF_SECONDS:
        raise ValueError(f"Unknown timeframe: {tf!r}. Known: {sorted(_TF_SECONDS)}")
    return _TF_SECONDS[tf]


def timeframe_ms(tf: str) -> int:
    return timeframe_seconds(tf) * 1000


def closed_bars(df: pd.DataFrame, timeframe: str, now_ms: Optional[int] = None) -> pd.DataFrame:
    """Return only fully-closed candles.

    A candle with open timestamp ``t`` closes at ``t + timeframe``. If that
    moment is still in the future relative to ``now_ms`` the candle is still
    forming and is removed. This prevents acting on a partial last bar.

    The DataFrame must have a UTC-ms integer index or a ``timestamp`` column
    (ms). Returns a copy.
    """
    if df is None or len(df) == 0:
        return df
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    tf_ms = timeframe_ms(timeframe)

    if "timestamp" in df.columns:
        ts = df["timestamp"].astype("int64")
    else:
        ts = pd.Series(df.index.astype("int64"), index=df.index)

    # Candle is closed when its close time (open + tf) <= now.
    mask = (ts + tf_ms) <= now_ms
    return df.loc[mask.values].copy()


def now_ms() -> int:
    return int(time.time() * 1000)

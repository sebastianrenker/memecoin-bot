"""Synthetic OHLCV generators for deterministic tests.

These are used ONLY in tests. Live/backtest paths use real data
(data.require_real: true) — synthetic candles never enter the paper trader.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def make_df(closes, timeframe_ms: int = 3_600_000, start_ms: int = 1_600_000_000_000,
            high_pad: float = 0.0, low_pad: float = 0.0) -> pd.DataFrame:
    """Build an OHLCV frame from a close series.

    open[i] = close[i-1] (gapless), high/low padded around the o/c range.
    """
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    opens = np.empty(n)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]
    highs = np.maximum(opens, closes) * (1 + high_pad)
    lows = np.minimum(opens, closes) * (1 - low_pad)
    ts = start_ms + np.arange(n) * timeframe_ms
    df = pd.DataFrame({
        "timestamp": ts.astype("int64"),
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": np.full(n, 1000.0),
    })
    df.index = df["timestamp"].values
    return df


def trend_up(n: int = 400, start: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    closes = start + np.arange(n) * step
    return make_df(closes, high_pad=0.001, low_pad=0.001)


def random_walk(n: int = 500, start: float = 100.0, vol: float = 0.02, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, vol, n)
    closes = start * np.exp(np.cumsum(rets))
    return make_df(closes, high_pad=0.003, low_pad=0.003)

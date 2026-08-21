"""Market-regime classification (trend vs range, high vs low volatility).

Used to ask: were the wins earned in the regime the strategy is meant for?
A trend strategy that only profits in ranges is suspicious.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

from core import indicators as ind


@dataclass
class RegimeResult:
    trend_frac: float          # fraction of bars in a trending regime
    high_vol_frac: float
    labels: pd.Series          # "trend" / "range" per bar


def classify(df: pd.DataFrame, adx_period: int = 14, adx_trend_min: float = 20.0,
             vol_window: int = 20) -> RegimeResult:
    _, _, adx = ind.dmi_adx(df, adx_period)
    trend_mask = adx >= adx_trend_min
    labels = pd.Series(np.where(trend_mask.fillna(False), "trend", "range"), index=df.index)

    ret = df["close"].pct_change()
    vol = ret.rolling(vol_window, min_periods=vol_window).std()
    med_vol = vol.median()
    high_vol = (vol > med_vol) if med_vol == med_vol else pd.Series(False, index=df.index)

    return RegimeResult(
        trend_frac=float(trend_mask.fillna(False).mean()),
        high_vol_frac=float(high_vol.fillna(False).mean()),
        labels=labels,
    )


def favorable_fraction(df: pd.DataFrame, trade_entry_indices: List[int],
                       is_trend_strategy: bool, **kw) -> float:
    """Fraction of trades entered in the regime the strategy targets."""
    if not trade_entry_indices:
        return 0.5  # unknown -> neutral
    reg = classify(df, **kw)
    want = "trend" if is_trend_strategy else "range"
    hits = 0
    for i in trade_entry_indices:
        if 0 <= i < len(reg.labels) and reg.labels.iloc[i] == want:
            hits += 1
    return hits / len(trade_entry_indices)

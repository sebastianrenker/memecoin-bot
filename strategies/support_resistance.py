from __future__ import annotations

import pandas as pd

from core import indicators as ind
from core.types import Signal, SignalType
from strategies.base import Strategy, register


@register("support_resistance")
class SupportResistance(Strategy):
    """Bounce long off a recent support level; exit into recent resistance.

    Counter-trend by nature, so treated as mean-reversion (down-weighted for
    memecoins). Support = rolling N-bar low, resistance = rolling N-bar high.
    """
    mean_reversion = True
    defaults = {"lookback": 30, "tol": 0.01, "atr_period": 14, "atr_mult": 2.0}

    @property
    def warmup(self) -> int:
        return int(self.p("lookback")) + int(self.p("atr_period")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        n = int(self.p("lookback"))
        support = df["low"].iloc[-(n + 1):-1].min()
        resistance = df["high"].iloc[-(n + 1):-1].max()
        a = ind.atr(df, int(self.p("atr_period")))
        if pd.isna(a.iloc[-1]) or support <= 0:
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        tol = float(self.p("tol"))
        close = df["close"]
        low = df["low"]

        near_support = low.iloc[-1] <= support * (1 + tol)
        bouncing = close.iloc[-1] > close.iloc[-2]
        if near_support and bouncing:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, confidence=0.75, reason="support bounce")
        if close.iloc[-1] >= resistance * (1 - tol):
            return Signal(SignalType.EXIT, atr=atr_val, reason="into resistance")
        return self._none()

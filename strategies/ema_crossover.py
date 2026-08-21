from __future__ import annotations

import pandas as pd

from core import indicators as ind
from core.types import Signal, SignalType
from strategies.base import Strategy, register


@register("ema_crossover")
class EmaCrossover(Strategy):
    """Long when fast EMA crosses above slow EMA; exit on the opposite cross.

    Trend-following. Stop distance = atr_mult * ATR on closed bars.
    """
    mean_reversion = False
    defaults = {"fast": 20, "slow": 50, "atr_period": 14, "atr_mult": 3.0}

    @property
    def warmup(self) -> int:
        return int(self.p("slow")) + int(self.p("atr_period")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        fast = ind.ema(df["close"], int(self.p("fast")))
        slow = ind.ema(df["close"], int(self.p("slow")))
        a = ind.atr(df, int(self.p("atr_period")))
        if fast.iloc[-1] != fast.iloc[-1] or slow.iloc[-1] != slow.iloc[-1]:
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))

        crossed_up = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]
        crossed_dn = fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]
        if crossed_up:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, reason="ema cross up")
        if crossed_dn:
            return Signal(SignalType.EXIT, atr=atr_val, reason="ema cross down")
        return self._none()

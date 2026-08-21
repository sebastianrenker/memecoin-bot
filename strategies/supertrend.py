from __future__ import annotations

import pandas as pd

from core import indicators as ind
from core.types import Signal, SignalType
from strategies.base import Strategy, register


@register("supertrend")
class Supertrend(Strategy):
    """Long when Supertrend flips to uptrend; exit when it flips to downtrend."""
    mean_reversion = False
    defaults = {"period": 10, "mult": 3.0, "atr_period": 14, "atr_mult": 3.0}

    @property
    def warmup(self) -> int:
        return int(self.p("period")) + int(self.p("atr_period")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        _, direction = ind.supertrend(df, int(self.p("period")), float(self.p("mult")))
        a = ind.atr(df, int(self.p("atr_period")))
        if a.iloc[-1] != a.iloc[-1]:
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))

        flip_up = direction.iloc[-2] == -1 and direction.iloc[-1] == 1
        flip_dn = direction.iloc[-2] == 1 and direction.iloc[-1] == -1
        if flip_up:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, reason="supertrend up")
        if flip_dn:
            return Signal(SignalType.EXIT, atr=atr_val, reason="supertrend down")
        return self._none()

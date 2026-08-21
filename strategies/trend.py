from __future__ import annotations

import pandas as pd

from core import indicators as ind
from core.types import Signal, SignalType
from strategies.base import Strategy, register


@register("dmi_trend")
class DmiTrend(Strategy):
    """+DI/-DI cross with an ADX strength gate."""
    mean_reversion = False
    defaults = {"period": 14, "adx_min": 20.0, "atr_period": 14, "atr_mult": 3.0}

    @property
    def warmup(self) -> int:
        return int(self.p("period")) * 3 + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        plus_di, minus_di, adx = ind.dmi_adx(df, int(self.p("period")))
        a = ind.atr(df, int(self.p("atr_period")))
        if any(pd.isna(x.iloc[-1]) for x in (plus_di, minus_di, adx, a)):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        strong = adx.iloc[-1] >= float(self.p("adx_min"))
        cross_up = plus_di.iloc[-2] <= minus_di.iloc[-2] and plus_di.iloc[-1] > minus_di.iloc[-1]
        cross_dn = plus_di.iloc[-2] >= minus_di.iloc[-2] and plus_di.iloc[-1] < minus_di.iloc[-1]
        if strong and cross_up:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, reason="dmi cross up")
        if cross_dn:
            return Signal(SignalType.EXIT, atr=atr_val, reason="dmi cross down")
        return self._none()

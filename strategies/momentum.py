from __future__ import annotations

import pandas as pd

from core import indicators as ind
from core.types import Signal, SignalType
from strategies.base import Strategy, register


@register("macd_momentum")
class MacdMomentum(Strategy):
    """MACD line crosses above signal while above zero -> long; opposite -> exit."""
    mean_reversion = False
    defaults = {"fast": 12, "slow": 26, "signal": 9, "atr_period": 14, "atr_mult": 3.0}

    @property
    def warmup(self) -> int:
        return int(self.p("slow")) + int(self.p("signal")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        macd_line, signal_line, _ = ind.macd(df["close"], int(self.p("fast")),
                                              int(self.p("slow")), int(self.p("signal")))
        a = ind.atr(df, int(self.p("atr_period")))
        if any(pd.isna(x.iloc[-1]) for x in (macd_line, signal_line, a)):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        cross_up = macd_line.iloc[-2] <= signal_line.iloc[-2] and macd_line.iloc[-1] > signal_line.iloc[-1]
        cross_dn = macd_line.iloc[-2] >= signal_line.iloc[-2] and macd_line.iloc[-1] < signal_line.iloc[-1]
        if cross_up and macd_line.iloc[-1] > 0:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, reason="macd cross up")
        if cross_dn:
            return Signal(SignalType.EXIT, atr=atr_val, reason="macd cross down")
        return self._none()


@register("roc_momentum")
class RocMomentum(Strategy):
    """Rate-of-change breakout: ROC above threshold -> long; below zero -> exit."""
    mean_reversion = False
    defaults = {"period": 12, "threshold": 5.0, "atr_period": 14, "atr_mult": 3.0}

    @property
    def warmup(self) -> int:
        return int(self.p("period")) + int(self.p("atr_period")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        r = ind.roc(df["close"], int(self.p("period")))
        a = ind.atr(df, int(self.p("atr_period")))
        if pd.isna(r.iloc[-1]) or pd.isna(a.iloc[-1]):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        thr = float(self.p("threshold"))
        if r.iloc[-2] <= thr and r.iloc[-1] > thr:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, reason="roc breakout")
        if r.iloc[-1] < 0:
            return Signal(SignalType.EXIT, atr=atr_val, reason="roc negative")
        return self._none()

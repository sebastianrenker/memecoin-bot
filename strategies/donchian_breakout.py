from __future__ import annotations

import pandas as pd

from core import indicators as ind
from core.types import Signal, SignalType
from strategies.base import Strategy, register


@register("donchian_breakout")
class DonchianBreakout(Strategy):
    """Long on a close above the prior N-bar high; exit below the M-bar low."""
    mean_reversion = False
    defaults = {"entry": 20, "exit": 10, "atr_period": 14, "atr_mult": 3.0}

    @property
    def warmup(self) -> int:
        return max(int(self.p("entry")), int(self.p("exit"))) + int(self.p("atr_period")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        # Channel from bars *excluding* the last closed bar, to avoid the
        # breakout bar being part of its own reference window.
        entry_hi = df["high"].iloc[-(int(self.p("entry")) + 1):-1].max()
        exit_lo = df["low"].iloc[-(int(self.p("exit")) + 1):-1].min()
        a = ind.atr(df, int(self.p("atr_period")))
        if a.iloc[-1] != a.iloc[-1]:
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        close = float(df["close"].iloc[-1])

        if close > entry_hi:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, reason="donchian breakout")
        if close < exit_lo:
            return Signal(SignalType.EXIT, atr=atr_val, reason="donchian exit")
        return self._none()

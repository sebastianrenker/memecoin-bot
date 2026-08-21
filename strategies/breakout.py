from __future__ import annotations

import datetime as dt

import pandas as pd

from core import indicators as ind
from core.types import Signal, SignalType
from strategies.base import Strategy, register


@register("bollinger_breakout")
class BollingerBreakout(Strategy):
    """Close above the upper Bollinger band -> long; back below the mid -> exit."""
    mean_reversion = False
    defaults = {"period": 20, "k": 2.0, "atr_period": 14, "atr_mult": 3.0}

    @property
    def warmup(self) -> int:
        return int(self.p("period")) + int(self.p("atr_period")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        lower, mid, upper = ind.bollinger(df["close"], int(self.p("period")), float(self.p("k")))
        a = ind.atr(df, int(self.p("atr_period")))
        if any(pd.isna(x.iloc[-1]) for x in (upper, mid, a)):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        close = df["close"]
        if close.iloc[-2] <= upper.iloc[-2] and close.iloc[-1] > upper.iloc[-1]:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, reason="bollinger breakout")
        if close.iloc[-1] < mid.iloc[-1]:
            return Signal(SignalType.EXIT, atr=atr_val, reason="back below mid")
        return self._none()


@register("keltner_pullback")
class KeltnerPullback(Strategy):
    """Uptrend (EMA rising) pullback to the lower Keltner band, then reclaim mid."""
    mean_reversion = False
    defaults = {"period": 20, "mult": 2.0, "atr_period": 14, "atr_mult": 3.0}

    @property
    def warmup(self) -> int:
        return int(self.p("period")) + int(self.p("atr_period")) + 10

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        lower, mid, upper = ind.keltner(df, int(self.p("period")), float(self.p("mult")))
        a = ind.atr(df, int(self.p("atr_period")))
        if any(pd.isna(x.iloc[-1]) for x in (lower, mid, a)) or pd.isna(mid.iloc[-6]):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        uptrend = mid.iloc[-1] > mid.iloc[-6]
        close = df["close"]
        touched_lower = (close.iloc[-4:-1] <= lower.iloc[-4:-1]).any()
        reclaim_mid = close.iloc[-2] < mid.iloc[-2] and close.iloc[-1] > mid.iloc[-1]
        if uptrend and touched_lower and reclaim_mid:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, reason="keltner pullback")
        if close.iloc[-1] < lower.iloc[-1]:
            return Signal(SignalType.EXIT, atr=atr_val, reason="lost lower band")
        return self._none()


@register("opening_range_breakout")
class OpeningRangeBreakout(Strategy):
    """Break above the first-N-bars range of the current UTC day."""
    mean_reversion = False
    defaults = {"or_bars": 6, "atr_period": 14, "atr_mult": 3.0}

    @property
    def warmup(self) -> int:
        return int(self.p("atr_period")) + int(self.p("or_bars")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup or "timestamp" not in df.columns:
            return self._none()
        a = ind.atr(df, int(self.p("atr_period")))
        if pd.isna(a.iloc[-1]):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))

        last_day = dt.datetime.fromtimestamp(int(df["timestamp"].iloc[-1]) / 1000,
                                             dt.timezone.utc).date()
        days = (df["timestamp"] // 1000).map(
            lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).date())
        today = df[days == last_day]
        or_bars = int(self.p("or_bars"))
        if len(today) <= or_bars:
            return self._none()  # opening range not yet complete
        or_high = today["high"].iloc[:or_bars].max()
        close = df["close"]
        prev_in_day = today["close"].iloc[-2] if len(today) >= 2 else close.iloc[-2]
        if prev_in_day <= or_high and close.iloc[-1] > or_high:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, reason="ORB up")
        return self._none()

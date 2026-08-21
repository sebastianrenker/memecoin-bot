"""Mean-reversion strategies.

MEMECOIN WARNING: mean reversion is *more* dangerous here. Memecoin moves often
run brutally further or collapse outright, so a dip is not a discount. The scorer
down-weights these (see stats/score.py) and confidence is discounted. Expect them
to underperform trend/breakout on memecoins — that is by design, not a bug.
"""
from __future__ import annotations

import pandas as pd

from core import indicators as ind
from core.types import Signal, SignalType
from strategies.base import Strategy, register


@register("rsi_mean_reversion")
class RsiMeanReversion(Strategy):
    mean_reversion = True
    defaults = {"period": 14, "oversold": 30.0, "exit_level": 55.0,
                "atr_period": 14, "atr_mult": 2.0}

    @property
    def warmup(self) -> int:
        return int(self.p("period")) * 3 + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        r = ind.rsi(df["close"], int(self.p("period")))
        a = ind.atr(df, int(self.p("atr_period")))
        if pd.isna(r.iloc[-1]) or pd.isna(a.iloc[-1]):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        if r.iloc[-2] >= float(self.p("oversold")) and r.iloc[-1] < float(self.p("oversold")):
            return Signal(SignalType.ENTER_LONG, atr=atr_val, confidence=0.8, reason="rsi oversold")
        if r.iloc[-1] > float(self.p("exit_level")):
            return Signal(SignalType.EXIT, atr=atr_val, reason="rsi recovered")
        return self._none()


@register("connors_rsi2")
class ConnorsRsi2(Strategy):
    """Classic Connors RSI(2): deep RSI(2) dip above a long SMA trend filter."""
    mean_reversion = True
    defaults = {"rsi_period": 2, "entry": 5.0, "sma_trend": 200, "exit_sma": 5,
                "atr_period": 14, "atr_mult": 2.0}

    @property
    def warmup(self) -> int:
        return int(self.p("sma_trend")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        close = df["close"]
        r2 = ind.rsi(close, int(self.p("rsi_period")))
        trend = ind.sma(close, int(self.p("sma_trend")))
        exit_sma = ind.sma(close, int(self.p("exit_sma")))
        a = ind.atr(df, int(self.p("atr_period")))
        if any(pd.isna(x.iloc[-1]) for x in (r2, trend, exit_sma, a)):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        if close.iloc[-1] > trend.iloc[-1] and r2.iloc[-1] < float(self.p("entry")):
            return Signal(SignalType.ENTER_LONG, atr=atr_val, confidence=0.8, reason="connors rsi2")
        if close.iloc[-1] > exit_sma.iloc[-1]:
            return Signal(SignalType.EXIT, atr=atr_val, reason="above exit sma")
        return self._none()


@register("stochastic_reversion")
class StochasticReversion(Strategy):
    mean_reversion = True
    defaults = {"k": 14, "d": 3, "oversold": 20.0, "overbought": 80.0,
                "atr_period": 14, "atr_mult": 2.0}

    @property
    def warmup(self) -> int:
        return int(self.p("k")) + int(self.p("d")) + int(self.p("atr_period")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        k, d = ind.stochastic(df, int(self.p("k")), int(self.p("d")))
        a = ind.atr(df, int(self.p("atr_period")))
        if any(pd.isna(x.iloc[-1]) for x in (k, d, a)):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        os = float(self.p("oversold"))
        if k.iloc[-2] <= os and k.iloc[-1] > os:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, confidence=0.8, reason="stoch up from oversold")
        if k.iloc[-1] > float(self.p("overbought")):
            return Signal(SignalType.EXIT, atr=atr_val, reason="stoch overbought")
        return self._none()


@register("williams_r_reversion")
class WilliamsRReversion(Strategy):
    mean_reversion = True
    defaults = {"period": 14, "oversold": -80.0, "exit_level": -20.0,
                "atr_period": 14, "atr_mult": 2.0}

    @property
    def warmup(self) -> int:
        return int(self.p("period")) + int(self.p("atr_period")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        wr = ind.williams_r(df, int(self.p("period")))
        a = ind.atr(df, int(self.p("atr_period")))
        if pd.isna(wr.iloc[-1]) or pd.isna(a.iloc[-1]):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        os = float(self.p("oversold"))
        if wr.iloc[-2] <= os and wr.iloc[-1] > os:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, confidence=0.8, reason="williams up from oversold")
        if wr.iloc[-1] > float(self.p("exit_level")):
            return Signal(SignalType.EXIT, atr=atr_val, reason="williams recovered")
        return self._none()


@register("cci_reversion")
class CciReversion(Strategy):
    mean_reversion = True
    defaults = {"period": 20, "oversold": -100.0, "exit_level": 0.0,
                "atr_period": 14, "atr_mult": 2.0}

    @property
    def warmup(self) -> int:
        return int(self.p("period")) + int(self.p("atr_period")) + 5

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.warmup:
            return self._none()
        c = ind.cci(df, int(self.p("period")))
        a = ind.atr(df, int(self.p("atr_period")))
        if pd.isna(c.iloc[-1]) or pd.isna(a.iloc[-1]):
            return self._none()
        atr_val = float(a.iloc[-1]) * float(self.p("atr_mult"))
        os = float(self.p("oversold"))
        if c.iloc[-2] <= os and c.iloc[-1] > os:
            return Signal(SignalType.ENTER_LONG, atr=atr_val, confidence=0.8, reason="cci up from oversold")
        if c.iloc[-1] > float(self.p("exit_level")):
            return Signal(SignalType.EXIT, atr=atr_val, reason="cci recovered")
        return self._none()

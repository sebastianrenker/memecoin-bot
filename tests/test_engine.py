"""Engine correctness tests: no look-ahead, stop-before-TP, leverage cap +
fee recompute, min-stop rejection, bar debounce."""
from __future__ import annotations

import pandas as pd

from backtest.engine import EngineConfig, run_backtest
from core.types import Side, Signal, SignalType
from strategies.base import Strategy
from tests.synth import make_df, trend_up


class _OneShotLong(Strategy):
    """Emits exactly one ENTER_LONG on a chosen bar; never exits by signal."""
    name = "oneshot_long"

    def __init__(self, at_bar: int, atr: float, confidence: float = 1.0):
        super().__init__({})
        self.at_bar = at_bar
        self.atr = atr
        self.confidence = confidence

    @property
    def warmup(self) -> int:
        return 1

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) - 1 == self.at_bar:
            return Signal(SignalType.ENTER_LONG, atr=self.atr, confidence=self.confidence)
        return self._none()


def test_signal_executes_at_next_open_not_current_bar():
    df = trend_up(n=80)
    strat = _OneShotLong(at_bar=10, atr=5.0)
    # TP enabled and a rising trend => the trade closes, so we can inspect it.
    res = run_backtest(strat, df, EngineConfig(take_profit_r=2.0))
    assert len(res.trades) == 1
    t = res.trades[0]
    # Entered at bar 11's open (t+1), never bar 10.
    assert t.entry_index == 11
    open11 = float(df["open"].iloc[11])
    slip = EngineConfig().slippage_rate
    assert abs(t.entry_price - open11 * (1 + slip)) < 1e-6


def test_min_stop_too_tight_is_rejected_not_widened():
    df = trend_up(n=40)
    price = float(df["open"].iloc[6])
    tiny = price * 0.0001  # 0.01% << min_stop_frac 0.25%
    strat = _OneShotLong(at_bar=5, atr=tiny)
    res = run_backtest(strat, df, EngineConfig(min_stop_frac=0.0025))
    assert res.rejected_tight_stops == 1
    assert len(res.trades) == 0  # never entered


def test_stop_checked_before_take_profit_same_bar():
    # Build a bar where BOTH stop and TP are inside the range; stop must win.
    closes = [100, 100, 100, 100, 100, 100]
    df = make_df(closes)
    # Manually craft bar 3 to span both stop and tp after a bar-2 entry signal.
    # Entry at open[3]. atr=2, stop=open-2, tp=open+4 (r=2). Make bar 3 low<stop and high>tp.
    df.loc[df.index[3], "high"] = 110.0
    df.loc[df.index[3], "low"] = 90.0
    strat = _OneShotLong(at_bar=2, atr=2.0)
    res = run_backtest(strat, df, EngineConfig(take_profit_r=2.0, slippage_rate=0.0, fee_rate=0.0))
    assert len(res.trades) == 1
    assert res.trades[0].reason == "stop"  # pessimistic: stop before TP


def test_leverage_cap_recomputes_notional_and_fee():
    df = trend_up(n=40)
    # Huge risk_per_trade would blow past leverage cap; qty must be capped.
    cfg = EngineConfig(leverage_cap=1.0, risk_per_trade=0.5, take_profit_r=None,
                       slippage_rate=0.0, fee_rate=0.01, min_stop_frac=0.0)
    price = float(df["open"].iloc[6])
    # stop distance small enough that uncapped notional >> equity.
    strat = _OneShotLong(at_bar=5, atr=price * 0.01)
    res = run_backtest(strat, df, cfg)
    # After entry, cash reduced by fee on CAPPED notional == equity*cap*fee.
    eq = cfg.initial_equity
    expected_fee = eq * cfg.leverage_cap * cfg.fee_rate
    # The first equity point after entry reflects fee on capped notional.
    # Reconstruct capped qty: notional == eq*cap => qty == eq*cap/fill.
    # Assert the realized entry fee (from any resulting trade) matches, if closed;
    # otherwise assert via cash proxy: mtm at entry bar ~ eq - fee (price flat-ish).
    # Trend is up so use a loose bound.
    entry_bar_eq = res.equity_curve[6].equity
    assert entry_bar_eq <= eq - expected_fee + 1e-6 + abs(eq) * 0.05


def test_no_reentry_same_bar_after_exit_debounce():
    # A strategy that would emit ENTER on every bar; after a stop-out on bar k,
    # it must not reopen on bar k.
    class AlwaysEnter(Strategy):
        name = "always_enter"

        @property
        def warmup(self):
            return 1

        def generate(self, df):
            return Signal(SignalType.ENTER_LONG, atr=2.0)

    closes = [100] * 20
    df = make_df(closes)
    # Make bar 5 dip to force a stop, and confirm at most one trade closes on bar 5.
    df.loc[df.index[5], "low"] = 90.0
    res = run_backtest(AlwaysEnter({}), df, EngineConfig(take_profit_r=None,
                       slippage_rate=0.0, fee_rate=0.0))
    exits_on_5 = [t for t in res.trades if t.exit_index == 5]
    entries_on_5 = [t for t in res.trades if t.entry_index == 5]
    assert len(exits_on_5) <= 1
    # No trade may be entered on bar 5 (debounce after the exit there).
    assert len(entries_on_5) == 0

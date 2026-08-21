"""Every listed strategy must register, produce valid signals, and survive a
full backtest without look-ahead errors."""
from __future__ import annotations

import numpy as np
import pytest

import strategies  # noqa: F401
from backtest.engine import EngineConfig, run_backtest
from core.types import SignalType
from strategies.base import available_strategies, build_strategy
from tests.synth import make_df

EXPECTED = {
    "ema_crossover", "supertrend", "donchian_breakout", "dmi_trend",
    "macd_momentum", "roc_momentum", "bollinger_breakout", "keltner_pullback",
    "opening_range_breakout", "rsi_mean_reversion", "connors_rsi2",
    "stochastic_reversion", "williams_r_reversion", "cci_reversion",
    "support_resistance",
}


def _market():
    x = np.linspace(0, 60, 1200)
    closes = 100 + 25 * np.sin(x / 3.0) + 0.03 * x ** 1.1 + 3 * np.sin(x)
    return make_df(closes, timeframe_ms=3_600_000, high_pad=0.004, low_pad=0.004)


def test_all_15_strategies_registered():
    assert EXPECTED <= set(available_strategies())


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_strategy_runs_through_engine(name):
    df = _market()
    strat = build_strategy(name, {})
    res = run_backtest(strat, df, EngineConfig(cost_multiplier=1.0))
    # Engine must complete and yield a full equity curve.
    assert len(res.equity_curve) == len(df)
    for t in res.trades:
        assert t.exit_index >= t.entry_index
        assert t.entry_index >= strat.warmup


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_signal_types_valid(name):
    df = _market()
    strat = build_strategy(name, {})
    sig = strat.generate(df)
    assert sig.type in set(SignalType)
    if sig.type in (SignalType.ENTER_LONG, SignalType.ENTER_SHORT):
        assert sig.atr >= 0

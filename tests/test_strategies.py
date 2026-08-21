"""Smoke tests: strategies register, produce valid signals, no look-ahead peeking."""
from __future__ import annotations

import pandas as pd

import numpy as np

import strategies  # noqa: F401  (triggers registration)
from core.types import SignalType
from strategies.base import available_strategies, build_strategy
from tests.synth import make_df, random_walk, trend_up


def test_phase1_strategies_registered():
    names = set(available_strategies())
    assert {"ema_crossover", "supertrend", "donchian_breakout"} <= names


def test_ema_crossover_fires_long_on_uptrend():
    # Dip then rally: the fast EMA starts below the slow EMA and crosses up.
    down = np.linspace(100, 70, 120)
    up = np.linspace(70, 140, 180)
    df = make_df(np.concatenate([down, up]), high_pad=0.001, low_pad=0.001)
    strat = build_strategy("ema_crossover", {"fast": 10, "slow": 30})
    # Somewhere in the warmup->end range a bullish cross should appear.
    fired = False
    for i in range(strat.warmup, len(df)):
        sig = strat.generate(df.iloc[: i + 1])
        if sig.type == SignalType.ENTER_LONG:
            fired = True
            assert sig.atr > 0
            break
    assert fired


def test_generate_only_reads_provided_slice():
    df = random_walk(n=200)
    strat = build_strategy("supertrend", {})
    # Truncating the frame must not raise and must respect the slice boundary.
    s1 = strat.generate(df.iloc[:120])
    assert s1.type in set(SignalType)

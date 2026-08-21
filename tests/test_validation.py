from __future__ import annotations

import numpy as np

from backtest.engine import EngineConfig
from backtest.montecarlo import monte_carlo
from backtest.walkforward import walk_forward
from stats.score import ScoreInputs, compute_score
from tests.synth import make_df


def test_monte_carlo_losing_edge_has_high_ruin():
    # A negative-expectancy R stream over a realistic horizon must ruin often.
    losers = ([-1.0] * 8 + [1.5] * 2) * 12   # 120 trades, avg R = -0.5
    res = monte_carlo(losers, risk_per_trade=0.02, runs=500, ruin_drawdown=0.3)
    assert res.ruin_prob > 0.5
    assert res.median_return < 0


def test_monte_carlo_positive_edge_lower_ruin():
    winners = ([1.2] * 6 + [-1.0] * 4) * 12  # 120 trades, avg R = +0.32
    res = monte_carlo(winners, risk_per_trade=0.01, runs=500, ruin_drawdown=0.5)
    assert res.ruin_prob < 0.2
    assert res.median_return > 0


def test_score_flags_low_trades_and_mean_reversion():
    s = compute_score(ScoreInputs(expectancy_r=0.1, profit_factor=1.4, n_trades=5,
                                   max_drawdown=0.2, is_mean_reversion=True))
    assert s.confidence < 0.5
    joined = " ".join(s.warnings)
    assert "noise" in joined and "mean-reversion" in joined
    assert "zero" in joined  # the memecoin reality-check warning is always present


def test_score_light_thresholds():
    strong = compute_score(ScoreInputs(expectancy_r=0.25, profit_factor=2.5, n_trades=80,
                                        max_drawdown=0.1, mc_ruin_prob=0.0,
                                        mc_ci_low_return=0.1, wf_efficiency=0.9,
                                        regime_favorable_frac=0.8, recency_expectancy_r=0.2))
    weak = compute_score(ScoreInputs(expectancy_r=-0.2, profit_factor=0.5, n_trades=80,
                                      max_drawdown=0.6))
    assert strong.total > weak.total
    assert weak.light == "red"


def test_walkforward_runs_and_reports_efficiency():
    # Deterministic sine-ish series; just check the machinery produces folds.
    x = np.linspace(0, 40, 800)
    closes = 100 + 20 * np.sin(x) + x  # trend + cycles
    df = make_df(closes, high_pad=0.002, low_pad=0.002)
    cfg = EngineConfig(cost_multiplier=1.0, min_stop_frac=0.0)
    res = walk_forward("ema_crossover", df, cfg,
                       {"fast": [10, 20], "slow": [40, 60]}, folds=3, min_trades=1)
    assert len(res.folds) >= 1
    assert 0.0 <= res.mean_efficiency <= 2.0

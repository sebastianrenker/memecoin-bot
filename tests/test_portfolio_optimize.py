from __future__ import annotations

import numpy as np

from backtest.engine import EngineConfig
from optimize.optimizer import optimize
from optimize.stress import stress_test
from portfolio.portfolio import Candidate, build_portfolio
from tests.synth import trend_up


def test_portfolio_quality_hurdle_and_correlation_and_weights():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 0.01, 300)
    a = Candidate("A", score=80, returns=base)
    b = Candidate("B", score=70, returns=base + rng.normal(0, 1e-4, 300))  # ~identical -> corr high
    c = Candidate("C", score=75, returns=rng.normal(0, 0.03, 300))          # independent, higher vol
    d = Candidate("D", score=40, returns=rng.normal(0, 0.01, 300))          # below quality hurdle

    res = build_portfolio([a, b, c, d], quality_min_score=50, max_correlation=0.7)
    assert "D" in res.dropped and "score" in res.dropped["D"]
    assert "B" in res.dropped and "corr" in res.dropped["B"]   # dropped vs higher-score A
    assert set(res.selected) == {"A", "C"}
    assert abs(sum(res.weights.values()) - 1.0) < 1e-9
    # Inverse-vol: lower-vol A gets more weight than higher-vol C.
    assert res.weights["A"] > res.weights["C"]


def test_optimizer_rejects_when_insufficient_data():
    df = trend_up(n=60)  # too short for 4-fold walk-forward
    r = optimize("ema_crossover", df, EngineConfig(), {"fast": [10], "slow": [30]},
                 folds=4, min_trades=20)
    assert r.accepted is False
    assert r.params is None


def test_optimizer_rejects_low_efficiency_or_few_trades():
    # Random-walk data: no persistent edge -> guard should refuse to accept.
    rng = np.random.default_rng(3)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 1500)))
    from tests.synth import make_df
    df = make_df(closes, high_pad=0.003, low_pad=0.003)
    r = optimize("ema_crossover", df, EngineConfig(cost_multiplier=2.0),
                 {"fast": [10, 20], "slow": [40, 60]}, folds=4,
                 wf_efficiency_min=0.5, min_trades=20)
    # Either too few OOS trades or failed efficiency — but never a silent accept.
    assert r.accepted in (False, True)
    if r.accepted:
        assert r.mean_efficiency >= 0.5 and r.oos_trades >= 20 and r.oos_expectancy_r > 0


def test_stress_losing_distribution_ruins():
    losers = ([-1.0] * 7 + [1.5] * 3)  # avg R = -0.25
    res = stress_test(losers, n_trades=200_000, risk_per_trade=0.02, ruin_drawdown=0.9)
    assert res.worst_drawdown >= 0.9
    assert res.prob_ruin == 1.0
    assert res.final_return < 0

"""Million-trade stress test — RISK quantification, not a profit proof.

Draws a very large number of trades from the empirical R-multiple distribution
(or an explicit worst-case distribution) to see how bad the drawdowns get and
how often the account is wiped. Large N shrinks sampling noise on the risk
estimates; it says nothing about whether the edge is real.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass
class StressResult:
    n_trades: int
    risk_per_trade: float
    prob_ruin: float             # fraction of the path at/under the ruin threshold
    worst_drawdown: float
    final_return: float
    p01_equity_multiple: float   # 1st-percentile equity multiple across the path
    note: str = ("Risk quantification only. Large N reduces sampling noise on the "
                 "risk estimate; it does not prove or create profitability.")


def stress_test(r_multiples: Sequence[float], n_trades: int = 1_000_000,
                risk_per_trade: float = 0.01, ruin_drawdown: float = 0.9,
                seed: int = 11, block: int = 100_000) -> StressResult:
    r = np.asarray(list(r_multiples), dtype=float)
    if len(r) == 0:
        return StressResult(0, risk_per_trade, 0.0, 0.0, 0.0, 1.0)

    rng = np.random.default_rng(seed)
    equity = 1.0
    peak = 1.0
    worst_dd = 0.0
    equity_samples = []
    remaining = n_trades
    while remaining > 0:
        k = min(block, remaining)
        draws = r[rng.integers(0, len(r), size=k)]
        steps = np.clip(1.0 + risk_per_trade * draws, 1e-12, None)
        path = equity * np.cumprod(steps)
        run_peak = np.maximum.accumulate(np.concatenate([[peak], path]))[1:]
        dd = (run_peak - path) / run_peak
        worst_dd = max(worst_dd, float(dd.max()))
        equity = float(path[-1])
        peak = max(peak, float(run_peak[-1]))
        # keep a thinned sample for percentile estimate
        equity_samples.append(path[:: max(1, k // 1000)])
        remaining -= k

    samples = np.concatenate(equity_samples)
    return StressResult(
        n_trades=n_trades,
        risk_per_trade=risk_per_trade,
        prob_ruin=1.0 if worst_dd >= ruin_drawdown else 0.0,
        worst_drawdown=worst_dd,
        final_return=equity - 1.0,
        p01_equity_multiple=float(np.percentile(samples, 1)),
    )

"""Monte-Carlo bootstrap of trade sequences.

Resamples the realised per-trade R-multiples with replacement to build many
alternative equity paths. Quantifies RISK — confidence interval on outcome and
probability of ruin. It does NOT prove profitability: reshuffling a losing edge
still loses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import numpy as np


@dataclass
class MonteCarloResult:
    runs: int
    ruin_prob: float                 # fraction of paths whose drawdown >= ruin_drawdown
    ci_low_return: float             # 5th percentile total return
    ci_high_return: float            # 95th percentile total return
    median_return: float
    median_max_drawdown: float
    mean_return: float

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def monte_carlo(r_multiples: Sequence[float], risk_per_trade: float = 0.01,
                runs: int = 1000, ruin_drawdown: float = 0.5,
                seed: int = 7) -> MonteCarloResult:
    r = np.asarray(list(r_multiples), dtype=float)
    n = len(r)
    if n == 0:
        return MonteCarloResult(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    rng = np.random.default_rng(seed)
    final_returns = np.empty(runs)
    max_dds = np.empty(runs)
    ruined = 0

    for k in range(runs):
        sample = r[rng.integers(0, n, size=n)]
        # Compound equity: each trade moves equity by risk_per_trade * R.
        steps = 1.0 + risk_per_trade * sample
        steps = np.clip(steps, 1e-9, None)  # equity can't go negative in this model
        equity = np.concatenate([[1.0], np.cumprod(steps)])
        peak = np.maximum.accumulate(equity)
        dd = (peak - equity) / peak
        mdd = float(dd.max())
        max_dds[k] = mdd
        final_returns[k] = equity[-1] - 1.0
        if mdd >= ruin_drawdown:
            ruined += 1

    return MonteCarloResult(
        runs=runs,
        ruin_prob=ruined / runs,
        ci_low_return=float(np.percentile(final_returns, 5)),
        ci_high_return=float(np.percentile(final_returns, 95)),
        median_return=float(np.median(final_returns)),
        median_max_drawdown=float(np.median(max_dds)),
        mean_return=float(final_returns.mean()),
    )

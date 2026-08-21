"""Self-optimization with an overfitting guard.

A parameter set is accepted ONLY if it clears all three gates:
  1. Out-of-sample validated (walk-forward, params fitted on train, scored on OOS).
  2. Walk-forward efficiency >= wf_efficiency_min (OOS holds up vs in-sample).
  3. Enough OOS trades (below that, the result is noise).

If nothing clears the gates, the honest answer is None — no parameters. We never
return the best in-sample fit and pretend it is validated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

import pandas as pd

from backtest.engine import EngineConfig
from backtest.walkforward import walk_forward


@dataclass
class OptimizeResult:
    accepted: bool
    params: Optional[Dict]
    mean_efficiency: float
    oos_trades: int
    oos_expectancy_r: float
    reason: str


def optimize(strategy_name: str, df: pd.DataFrame, cfg: EngineConfig,
             param_grid: Dict[str, Sequence], folds: int = 4,
             wf_efficiency_min: float = 0.5, min_trades: int = 20) -> OptimizeResult:
    wf = walk_forward(strategy_name, df, cfg, param_grid, folds=folds,
                      min_trades=max(1, min_trades // folds))

    if not wf.folds:
        return OptimizeResult(False, None, 0.0, 0, 0.0,
                              "insufficient data for walk-forward")

    if wf.oos_trades < min_trades:
        return OptimizeResult(False, None, wf.mean_efficiency, wf.oos_trades,
                              wf.oos_expectancy_r,
                              f"only {wf.oos_trades} OOS trades < {min_trades} (noise)")

    if wf.mean_efficiency < wf_efficiency_min:
        return OptimizeResult(False, None, wf.mean_efficiency, wf.oos_trades,
                              wf.oos_expectancy_r,
                              f"WF efficiency {wf.mean_efficiency:.2f} < {wf_efficiency_min} (overfit)")

    if wf.oos_expectancy_r <= 0:
        return OptimizeResult(False, None, wf.mean_efficiency, wf.oos_trades,
                              wf.oos_expectancy_r, "non-positive OOS expectancy")

    # Use the most recent fold's chosen params as the forward-going setting.
    chosen = wf.folds[-1].params
    return OptimizeResult(True, chosen, wf.mean_efficiency, wf.oos_trades,
                          wf.oos_expectancy_r, "validated OOS")

"""Walk-forward validation.

Parameters are chosen on the TRAIN slice only; only the out-of-sample TEST
slice is scored. Walk-forward efficiency (OOS / IS performance) exposes
overfitting: a strategy that only works in-sample gets an efficiency near zero.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

from backtest.engine import EngineConfig, run_backtest
from stats.metrics import compute_metrics
from strategies.base import build_strategy


@dataclass
class WFFold:
    params: Dict
    is_return: float
    oos_return: float
    oos_trades: int
    efficiency: float


@dataclass
class WalkForwardResult:
    folds: List[WFFold] = field(default_factory=list)
    mean_efficiency: float = 0.0
    oos_trades: int = 0
    oos_expectancy_r: float = 0.0
    oos_returns: List[float] = field(default_factory=list)

    @property
    def passed_efficiency(self) -> bool:
        return self.mean_efficiency >= 0.5


def _grid(param_grid: Dict[str, Sequence]) -> List[Dict]:
    if not param_grid:
        return [{}]
    keys = list(param_grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*[param_grid[k] for k in keys])]


def _score_default(metrics, min_trades: int) -> float:
    if metrics.n_trades < min_trades:
        return float("-inf")
    return metrics.expectancy_r


def walk_forward(strategy_name: str, df: pd.DataFrame, cfg: EngineConfig,
                 param_grid: Dict[str, Sequence], folds: int = 4,
                 train_frac: float = 0.6, min_trades: int = 5,
                 objective: Optional[Callable] = None) -> WalkForwardResult:
    objective = objective or _score_default
    n = len(df)
    res = WalkForwardResult()
    if n < (folds + 1) * 20:
        return res  # not enough data -> honest empty result

    seg = n // (folds + 1)
    grid = _grid(param_grid)
    all_oos_r: List[float] = []

    for f in range(folds):
        train = df.iloc[f * seg:(f + 1) * seg].reset_index(drop=True)
        test = df.iloc[(f + 1) * seg:(f + 2) * seg].reset_index(drop=True)
        if len(train) < 20 or len(test) < 20:
            continue

        # Optimise on TRAIN only.
        best_params, best_obj, best_is_ret = None, float("-inf"), 0.0
        for params in grid:
            strat = build_strategy(strategy_name, params)
            r = run_backtest(strat, train, cfg)
            m = compute_metrics(r.trades, r.equity_curve, cfg.initial_equity)
            o = objective(m, min_trades)
            if o > best_obj:
                best_obj, best_params, best_is_ret = o, params, m.total_return
        if best_params is None:
            continue

        # Evaluate the chosen params on TEST (OOS) only.
        strat = build_strategy(strategy_name, best_params)
        r = run_backtest(strat, test, cfg)
        m = compute_metrics(r.trades, r.equity_curve, cfg.initial_equity)
        all_oos_r.extend(t.r_multiple for t in r.trades)

        # Efficiency: OOS return relative to IS return (clipped to [0, 2]).
        if best_is_ret > 1e-9:
            eff = max(0.0, min(2.0, m.total_return / best_is_ret))
        else:
            eff = 1.0 if m.total_return >= 0 else 0.0
        res.folds.append(WFFold(best_params, best_is_ret, m.total_return, m.n_trades, eff))

    if res.folds:
        res.mean_efficiency = sum(f.efficiency for f in res.folds) / len(res.folds)
        res.oos_trades = sum(f.oos_trades for f in res.folds)
        res.oos_returns = [f.oos_return for f in res.folds]
        res.oos_expectancy_r = (sum(all_oos_r) / len(all_oos_r)) if all_oos_r else 0.0
    return res

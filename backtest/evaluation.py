"""End-to-end evaluation of one (strategy, symbol): backtest + walk-forward +
Monte-Carlo + regime -> the transparent works-now score.

Real data only. If data can't be fetched the combo is skipped (returns None),
never fabricated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from backtest.engine import EngineConfig, run_backtest
from backtest.montecarlo import monte_carlo
from backtest.regime import favorable_fraction
from backtest.walkforward import walk_forward
from core.utils import closed_bars
from data.base import DataUnavailable
from stats.metrics import compute_metrics
from stats.score import ScoreInputs, compute_score
from strategies.base import build_strategy

# Small, honest parameter grids for walk-forward / optimization.
PARAM_GRIDS: Dict[str, Dict[str, List[Any]]] = {
    "ema_crossover": {"fast": [10, 20], "slow": [40, 60]},
    "supertrend": {"period": [7, 10], "mult": [2.0, 3.0]},
    "donchian_breakout": {"entry": [20, 40], "exit": [10, 20]},
    "dmi_trend": {"period": [14], "adx_min": [18.0, 25.0]},
    "macd_momentum": {"fast": [12], "slow": [26], "signal": [9]},
    "roc_momentum": {"period": [10, 14], "threshold": [3.0, 6.0]},
    "bollinger_breakout": {"period": [20], "k": [2.0, 2.5]},
    "keltner_pullback": {"period": [20], "mult": [1.5, 2.0]},
    "opening_range_breakout": {"or_bars": [4, 6]},
    "rsi_mean_reversion": {"period": [14], "oversold": [25.0, 30.0]},
    "connors_rsi2": {"entry": [5.0, 10.0], "sma_trend": [100, 200]},
    "stochastic_reversion": {"k": [14], "oversold": [15.0, 20.0]},
    "williams_r_reversion": {"period": [14], "oversold": [-85.0, -80.0]},
    "cci_reversion": {"period": [20], "oversold": [-120.0, -100.0]},
    "support_resistance": {"lookback": [20, 30], "tol": [0.01, 0.02]},
}


@dataclass
class Evaluation:
    strategy: str
    symbol: str
    score: float
    light: str
    expectancy_r: float
    n_trades: int
    max_drawdown: float
    mean_efficiency: float
    ruin_prob: float
    total_return: float
    warnings: List[str]
    subscores: Dict[str, float]
    params: Dict[str, Any]
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy, "symbol": self.symbol, "score": self.score,
            "light": self.light, "expectancy_r": self.expectancy_r, "n_trades": self.n_trades,
            "mean_efficiency": self.mean_efficiency, "ruin_prob": self.ruin_prob,
            "extra": {"max_drawdown": self.max_drawdown, "total_return": self.total_return,
                      "warnings": self.warnings, "subscores": self.subscores,
                      "params": self.params},
        }


def evaluate_combo(strategy_name: str, symbol: str, df_raw: pd.DataFrame,
                   cfg: EngineConfig, settings=None, timeframe: str = "1h",
                   now_ms: Optional[int] = None) -> Optional[Evaluation]:
    df = closed_bars(df_raw, timeframe, now_ms)
    if df is None or len(df) < 100:
        return None
    df.attrs["symbol"] = symbol

    strat = build_strategy(strategy_name, {})
    res = run_backtest(strat, df, cfg)
    m = compute_metrics(res.trades, res.equity_curve, cfg.initial_equity)

    grid = PARAM_GRIDS.get(strategy_name, {})
    folds = int((settings.get("validation.walkforward.folds", 4)) if settings else 4)
    wf = walk_forward(strategy_name, df, cfg, grid, folds=folds, min_trades=1)

    r_for_mc = ([t.r_multiple for t in res.trades])
    mc = monte_carlo(r_for_mc, risk_per_trade=cfg.risk_per_trade,
                     runs=int(settings.get("validation.montecarlo.runs", 1000)) if settings else 1000,
                     ruin_drawdown=float(settings.get("validation.montecarlo.ruin_drawdown", 0.5)) if settings else 0.5)

    entry_idx = [t.entry_index for t in res.trades]
    fav = favorable_fraction(df, entry_idx, is_trend_strategy=not strat.mean_reversion)

    # Recency: expectancy of the most recent third of trades.
    recency_r = None
    if len(res.trades) >= 6:
        tail = res.trades[-max(3, len(res.trades) // 3):]
        recency_r = sum(t.r_multiple for t in tail) / len(tail)

    si = ScoreInputs(
        expectancy_r=m.expectancy_r, profit_factor=m.profit_factor, n_trades=m.n_trades,
        max_drawdown=m.max_drawdown, mc_ruin_prob=mc.ruin_prob,
        mc_ci_low_return=mc.ci_low_return, wf_efficiency=(wf.mean_efficiency if wf.folds else None),
        regime_favorable_frac=fav, recency_expectancy_r=recency_r,
        is_mean_reversion=strat.mean_reversion)
    weights = settings.get("score.weights") if settings else None
    green = float(settings.get("score.green_min", 65)) if settings else 65.0
    yellow = float(settings.get("score.yellow_min", 45)) if settings else 45.0
    score = compute_score(si, weights=weights, green_min=green, yellow_min=yellow)

    return Evaluation(
        strategy=strategy_name, symbol=symbol, score=score.total, light=score.light,
        expectancy_r=round(m.expectancy_r, 4), n_trades=m.n_trades,
        max_drawdown=round(m.max_drawdown, 4), mean_efficiency=round(wf.mean_efficiency, 3),
        ruin_prob=round(mc.ruin_prob, 4), total_return=round(m.total_return, 4),
        warnings=score.warnings, subscores=score.subscores,
        params=(wf.folds[-1].params if wf.folds else {}),
        extra={"mc_ci_low": mc.ci_low_return, "mc_ci_high": mc.ci_high_return,
               "regime_favorable_frac": fav})

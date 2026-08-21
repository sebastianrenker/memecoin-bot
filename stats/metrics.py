"""Performance metrics computed from trades and equity curves.

Every metric is descriptive of the *simulated* backtest only. None of it is a
prediction. Memecoin samples are short and noisy — treat all numbers with
suspicion and always alongside trade count and drawdown.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np

from core.types import EquityPoint, Trade


@dataclass
class Metrics:
    n_trades: int
    win_rate: float
    profit_factor: float
    expectancy_r: float          # mean R per trade
    total_return: float          # final/initial - 1
    max_drawdown: float          # peak-to-trough on equity curve (fraction)
    sharpe: float                # per-trade Sharpe (not annualized; noise-prone)
    avg_r: float
    std_r: float
    gross_profit: float
    gross_loss: float

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def equity_drawdown(curve: Sequence[EquityPoint]) -> float:
    if not curve:
        return 0.0
    peak = -math.inf
    max_dd = 0.0
    for p in curve:
        peak = max(peak, p.equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - p.equity) / peak)
    return max_dd


def compute_metrics(trades: List[Trade], curve: Sequence[EquityPoint],
                    initial_equity: float) -> Metrics:
    n = len(trades)
    if n == 0:
        final = curve[-1].equity if curve else initial_equity
        return Metrics(0, 0.0, 0.0, 0.0, final / initial_equity - 1.0 if initial_equity else 0.0,
                       equity_drawdown(curve), 0.0, 0.0, 0.0, 0.0, 0.0)

    rs = np.array([t.r_multiple for t in trades], dtype=float)
    pnls = np.array([t.pnl for t in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    win_rate = float((pnls > 0).mean())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    avg_r = float(rs.mean())
    std_r = float(rs.std(ddof=1)) if n > 1 else 0.0
    sharpe = avg_r / std_r * math.sqrt(n) if std_r > 0 else 0.0
    final = curve[-1].equity if curve else initial_equity
    total_return = final / initial_equity - 1.0 if initial_equity else 0.0

    return Metrics(
        n_trades=n, win_rate=win_rate, profit_factor=profit_factor,
        expectancy_r=avg_r, total_return=total_return,
        max_drawdown=equity_drawdown(curve), sharpe=sharpe,
        avg_r=avg_r, std_r=std_r, gross_profit=gross_profit, gross_loss=gross_loss,
    )

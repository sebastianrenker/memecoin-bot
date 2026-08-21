"""Portfolio construction across (strategy, symbol) combinations.

Applies quality hurdles, drops highly-correlated pairs, and weights the
survivors by inverse volatility. Diversification LOWERS drawdown and smooths
equity — it does NOT turn losers into winners. If the underlying combos have no
edge, a portfolio of them still has no edge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class Candidate:
    key: str                      # e.g. "ema_crossover@DOGE/USDT"
    score: float                  # works-now score 0..100
    returns: np.ndarray           # per-period returns (aligned length preferred)


@dataclass
class PortfolioResult:
    weights: Dict[str, float]
    selected: List[str]
    dropped: Dict[str, str]       # key -> reason
    method: str

    def as_dict(self) -> dict:
        return {"weights": self.weights, "selected": self.selected,
                "dropped": self.dropped, "method": self.method}


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    m = min(len(a), len(b))
    if m < 3:
        return 0.0
    a, b = a[-m:], b[-m:]
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def build_portfolio(candidates: List[Candidate], quality_min_score: float = 50.0,
                    max_correlation: float = 0.7,
                    method: str = "inverse_vol") -> PortfolioResult:
    dropped: Dict[str, str] = {}

    # 1) Quality hurdle.
    survivors = []
    for c in sorted(candidates, key=lambda x: x.score, reverse=True):
        if c.score < quality_min_score:
            dropped[c.key] = f"score {c.score:.1f} < quality_min {quality_min_score:.1f}"
        else:
            survivors.append(c)

    # 2) Correlation filter (greedy: keep higher score, drop correlated lower).
    kept: List[Candidate] = []
    for c in survivors:  # already score-desc
        redundant = None
        for k in kept:
            if _corr(c.returns, k.returns) > max_correlation:
                redundant = k.key
                break
        if redundant is not None:
            dropped[c.key] = f"corr > {max_correlation:.2f} with {redundant}"
        else:
            kept.append(c)

    # 3) Weighting.
    weights: Dict[str, float] = {}
    if kept:
        if method == "inverse_vol":
            inv = []
            for c in kept:
                vol = float(np.std(c.returns)) if len(c.returns) > 1 else 0.0
                inv.append(1.0 / vol if vol > 1e-12 else 0.0)
            total = sum(inv)
            if total > 0:
                weights = {c.key: w / total for c, w in zip(kept, inv)}
            else:
                weights = {c.key: 1.0 / len(kept) for c in kept}
        else:  # equal weight
            weights = {c.key: 1.0 / len(kept) for c in kept}

    return PortfolioResult(weights=weights, selected=[c.key for c in kept],
                           dropped=dropped, method=method)

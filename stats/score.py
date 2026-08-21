"""The transparent "is this working right now?" score.

Score = weighted(Edge, Robustness, Regime, Recency) x ConfidenceFactor, mapped
to a traffic light with explicit warnings. It is a *descriptive* summary of past
simulated behaviour, NOT a prediction and NOT advice. A green light on a memecoin
is still a bet on something that most likely trends to zero.

Every sub-score is in 0..100 and every input is spelled out so the number can
always be traced back to its parts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class ScoreInputs:
    expectancy_r: float                 # OOS mean R
    profit_factor: float
    n_trades: int
    max_drawdown: float                 # fraction
    # Robustness (optional, from MC / walk-forward)
    mc_ruin_prob: Optional[float] = None        # 0..1
    mc_ci_low_return: Optional[float] = None     # 5th pct total return
    wf_efficiency: Optional[float] = None        # OOS/IS ratio
    # Regime: fraction of OOS trades taken in a favourable regime, 0..1
    regime_favorable_frac: Optional[float] = None
    # Recency: recent-window expectancy_r vs overall
    recency_expectancy_r: Optional[float] = None
    is_mean_reversion: bool = False


@dataclass
class Score:
    total: float
    light: str                          # "green" | "yellow" | "red"
    subscores: Dict[str, float]
    confidence: float
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total": self.total, "light": self.light, "confidence": self.confidence,
            "subscores": self.subscores, "warnings": self.warnings,
        }


def _edge_score(i: ScoreInputs) -> float:
    # Expectancy in R dominates; profit factor refines.
    e = 50.0 + 250.0 * i.expectancy_r          # +0.2R -> 100, -0.2R -> 0
    pf = 0.0
    if i.profit_factor is not None:
        pf = _clip((i.profit_factor - 1.0) * 50.0)  # PF 1.0->0, 3.0->100
    return _clip(0.7 * _clip(e) + 0.3 * pf)


def _robustness_score(i: ScoreInputs) -> float:
    parts, weights = [], []
    if i.mc_ruin_prob is not None:
        parts.append(_clip(100.0 * (1.0 - i.mc_ruin_prob))); weights.append(0.45)
    if i.mc_ci_low_return is not None:
        # CI-low return >= 0 is good; -50% -> 0.
        parts.append(_clip(100.0 + 200.0 * i.mc_ci_low_return)); weights.append(0.30)
    if i.wf_efficiency is not None:
        parts.append(_clip(i.wf_efficiency * 100.0)); weights.append(0.25)
    if not parts:
        return 50.0  # unknown -> neutral
    tot = sum(w for w in weights)
    return sum(p * w for p, w in zip(parts, weights)) / tot


def _regime_score(i: ScoreInputs) -> float:
    if i.regime_favorable_frac is None:
        return 50.0
    return _clip(i.regime_favorable_frac * 100.0)


def _recency_score(i: ScoreInputs) -> float:
    if i.recency_expectancy_r is None:
        return 50.0
    return _clip(50.0 + 250.0 * i.recency_expectancy_r)


def _confidence(i: ScoreInputs) -> float:
    # Few trades -> low confidence. Mean-reversion on memecoins -> discounted.
    c = min(1.0, i.n_trades / 50.0)            # 50+ trades -> full
    if i.n_trades < 20:
        c *= 0.6
    if i.is_mean_reversion:
        c *= 0.7                                # memecoins punish MR harder
    if i.max_drawdown >= 0.5:
        c *= 0.7
    return max(0.05, c)


def compute_score(i: ScoreInputs, weights: Optional[Dict[str, float]] = None,
                  green_min: float = 65.0, yellow_min: float = 45.0) -> Score:
    weights = weights or {"edge": 0.35, "robustness": 0.25, "regime": 0.20, "recency": 0.20}
    sub = {
        "edge": _edge_score(i),
        "robustness": _robustness_score(i),
        "regime": _regime_score(i),
        "recency": _recency_score(i),
    }
    wsum = sum(weights.values()) or 1.0
    base = sum(sub[k] * weights.get(k, 0.0) for k in sub) / wsum
    conf = _confidence(i)
    total = _clip(base * conf)

    warnings: List[str] = []
    if i.n_trades < 20:
        warnings.append(f"only {i.n_trades} trades - result is likely noise, not signal")
    if i.expectancy_r <= 0:
        warnings.append("non-positive expectancy in the sample")
    if i.max_drawdown >= 0.3:
        warnings.append(f"deep simulated drawdown ({i.max_drawdown:.0%})")
    if i.mc_ruin_prob is not None and i.mc_ruin_prob > 0.05:
        warnings.append(f"Monte-Carlo ruin probability {i.mc_ruin_prob:.0%}")
    if i.is_mean_reversion:
        warnings.append("mean-reversion on memecoins is dangerous — trends run or collapse")
    warnings.append("memecoins mostly go to zero; a positive short-term result is not an edge")

    light = "green" if total >= green_min else ("yellow" if total >= yellow_min else "red")
    return Score(total=round(total, 1), light=light, subscores={k: round(v, 1) for k, v in sub.items()},
                 confidence=round(conf, 3), warnings=warnings)

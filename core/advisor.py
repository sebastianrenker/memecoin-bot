"""A free, local, transparent decision/analysis layer ("the AI").

HONEST FRAMING: there is no free (or paid) AI that reliably trades memecoins
profitably. Anything sold as such is hype, overfit, or a scam. What this module
does instead is turn the bot's OWN numbers — the walk-forward score, the rug
verdict, and the current attention signal — into a clear, reproducible
recommendation with reasons. It is deterministic and offline by default.

Optionally, if you run a free local LLM via Ollama (https://ollama.com), it can
phrase the same facts in natural language — purely cosmetic. The LLM never
invents a trade decision and never sees real money. Every recommendation is for
SIMULATED (paper) money only; live trading stays locked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from data.memecoin_filters import FilterVerdict

DISCLAIMER = ("Paper only. Not a prediction, not advice. Most memecoins go to zero; "
              "a good score is descriptive of the past, not a promise. Verify on "
              "RugCheck/GMGN before ever risking real money.")


@dataclass
class Advice:
    action: str                 # "avoid" | "watch" | "paper_consider"
    confidence: float           # 0..1
    reasons: List[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER

    def as_dict(self) -> dict:
        return {"action": self.action, "confidence": round(self.confidence, 2),
                "reasons": self.reasons, "disclaimer": self.disclaimer}


def advise(*, works_now_score: Optional[float] = None, light: Optional[str] = None,
           rug_verdict: Optional[FilterVerdict] = None, attention: Optional[float] = None,
           mean_reversion: bool = False, n_trades: Optional[int] = None,
           ruin_prob: Optional[float] = None) -> Advice:
    """Combine the bot's own evidence into a paper-only recommendation.

    Order of authority: a failed rug check overrides everything (avoid). Then
    edge (score) and confidence (trades/ruin) decide watch vs. paper_consider.
    """
    reasons: List[str] = []

    # 1) Safety gate dominates.
    if rug_verdict is not None and not rug_verdict.passed:
        reasons.append("rug filter FAILED: " + "; ".join(rug_verdict.reasons[:3]))
        return Advice("avoid", 0.9, reasons)

    if rug_verdict is not None and rug_verdict.passed and rug_verdict.checked >= 6:
        reasons.append(f"passed {rug_verdict.checked} rug checks")

    # 2) Edge from the works-now score.
    score = works_now_score if works_now_score is not None else (
        70.0 if light == "green" else 50.0 if light == "yellow" else 25.0 if light else None)
    if score is None:
        reasons.append("no strategy evaluation available yet")
        action, conf = "watch", 0.3
    else:
        reasons.append(f"works-now score {score:.0f}")
        if score >= 65:
            action, conf = "paper_consider", 0.6
        elif score >= 45:
            action, conf = "watch", 0.45
        else:
            action, conf = "avoid", 0.6
            reasons.append("weak/negative simulated edge")

    # 3) Confidence dampers (never turn avoid into consider).
    if n_trades is not None and n_trades < 20:
        conf *= 0.6
        reasons.append(f"only {n_trades} trades - low confidence")
        if action == "paper_consider":
            action = "watch"
    if ruin_prob is not None and ruin_prob > 0.05:
        conf *= 0.7
        reasons.append(f"Monte-Carlo ruin prob {ruin_prob:.0%}")
        if action == "paper_consider":
            action = "watch"
    if mean_reversion:
        conf *= 0.8
        reasons.append("mean-reversion is more dangerous on memecoins")

    if attention is not None:
        reasons.append(f"current attention {attention:.0f}/100 (activity, not a forecast)")

    return Advice(action, max(0.05, min(1.0, conf)), reasons)


def ollama_summary(advice: Advice, context: str = "", model: str = "llama3.2",
                   host: str = "http://localhost:11434", timeout: float = 30.0) -> Optional[str]:
    """Optional: phrase the advice via a FREE local Ollama model. None if unavailable.

    Cosmetic only — the decision in ``advice`` is already made deterministically.
    """
    try:
        import json

        import requests
        prompt = (
            "You are a blunt, honest risk assistant for a PAPER-ONLY memecoin tool. "
            "Do NOT predict prices or promise profit. In 2-3 sentences, restate this "
            "recommendation and its reasons plainly, and remind the reader it is paper "
            "money and most memecoins go to zero.\n\n"
            f"Recommendation: {advice.action} (confidence {advice.confidence:.0%}).\n"
            f"Reasons: {'; '.join(advice.reasons)}.\n"
            f"Context: {context}\n")
        r = requests.post(f"{host}/api/generate",
                          json={"model": model, "prompt": prompt, "stream": False},
                          timeout=timeout)
        if r.status_code != 200:
            return None
        return (r.json() or {}).get("response", "").strip() or None
    except Exception:
        return None

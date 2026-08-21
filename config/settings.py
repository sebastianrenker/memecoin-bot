"""Typed access to config.yaml plus factory functions.

Config values must reach the executing classes — we build them through
factories (build_engine_config, ...) rather than relying on class defaults.
``Settings.validate()`` fails fast on nonsensical or unsafe configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List

import yaml

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


class ConfigError(ValueError):
    pass


@dataclass
class Settings:
    raw: Dict[str, Any]
    path: str = _DEFAULT_PATH

    # ---- loading ---------------------------------------------------------
    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        path = path or os.environ.get("MEMEBOT_CONFIG", _DEFAULT_PATH)
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        s = cls(raw=raw, path=path)
        return s

    # ---- dotted access ---------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def mode(self) -> str:
        return str(self.raw.get("mode", "paper")).lower()

    @property
    def universe(self) -> List[str]:
        return list(self.get("data.universe", []) or [])

    # ---- validation ------------------------------------------------------
    def validate(self) -> List[str]:
        """Return a list of problems; empty list means OK. Raises on hard errors."""
        problems: List[str] = []

        if self.mode not in ("paper", "live"):
            problems.append(f"mode must be 'paper' or 'live', got {self.mode!r}")
        if self.mode == "live":
            problems.append("mode: live is not supported — live trading is locked. Use paper.")

        rpt = float(self.get("engine.risk_per_trade", 0.01))
        if not (0 < rpt <= 0.02):
            problems.append(f"engine.risk_per_trade must be in (0, 0.02]; got {rpt}")

        lev = float(self.get("engine.leverage_cap", 1.0))
        if not (0 < lev <= 5):
            problems.append(f"engine.leverage_cap must be in (0, 5]; got {lev}")

        mstop = float(self.get("engine.min_stop_frac", 0.005))
        if mstop <= 0:
            problems.append("engine.min_stop_frac must be > 0 (guards the ATR≈0 stop loop)")

        dl = float(self.get("risk.daily_loss_limit", 0.03))
        if not (0 < dl < 1):
            problems.append(f"risk.daily_loss_limit must be in (0, 1); got {dl}")

        kill = float(self.get("risk.max_drawdown_kill", 0.25))
        if not (0 < kill < 1):
            problems.append(f"risk.max_drawdown_kill must be in (0, 1); got {kill}")

        if float(self.get("engine.cost_multiplier", 1.0)) < 1.0:
            problems.append("engine.cost_multiplier < 1.0 is optimistic; use >= 1.0 (2.0 recommended)")

        if not self.get("data.require_real", True):
            problems.append("data.require_real is false — this tool must use real data only")

        if not self.universe and not self.get("data.auto_discovery.enabled", False):
            problems.append("no universe configured and auto_discovery disabled")

        return problems


# ---- factories -----------------------------------------------------------
def build_engine_config(s: Settings):
    from backtest.engine import EngineConfig
    e = s.get("engine", {}) or {}
    return EngineConfig(
        initial_equity=float(e.get("initial_equity", 10_000.0)),
        fee_rate=float(e.get("fee_rate", 0.002)),
        slippage_rate=float(e.get("slippage_rate", 0.003)),
        risk_per_trade=float(e.get("risk_per_trade", 0.01)),
        leverage_cap=float(e.get("leverage_cap", 1.0)),
        min_stop_frac=float(e.get("min_stop_frac", 0.005)),
        take_profit_r=(None if e.get("take_profit_r") in (None, 0, False)
                       else float(e.get("take_profit_r"))),
        allow_short=bool(e.get("allow_short", False)),
        cost_multiplier=float(e.get("cost_multiplier", 2.0)),
    )


def build_risk_config(s: Settings):
    from risk.manager import RiskConfig
    r = s.get("risk", {}) or {}
    return RiskConfig(
        max_open_positions=int(r.get("max_open_positions", 5)),
        daily_loss_limit=float(r.get("daily_loss_limit", 0.03)),
        max_drawdown_kill=float(r.get("max_drawdown_kill", 0.25)),
        min_stop_frac=float(s.get("engine.min_stop_frac", 0.005)),
    )

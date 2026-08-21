"""Strategy base class, parameter handling, and a name->class registry.

Config values reach the executing classes via the factory ``build_strategy`` —
we never rely on hidden defaults. A strategy consumes a DataFrame of *closed*
candles and returns a single Signal describing what to do at the next open.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Type

import pandas as pd

from core.types import Signal, SignalType

_REGISTRY: Dict[str, Type["Strategy"]] = {}


def register(name: str):
    def deco(cls: Type["Strategy"]):
        cls.name = name
        _REGISTRY[name] = cls
        return cls
    return deco


def available_strategies() -> Dict[str, Type["Strategy"]]:
    return dict(_REGISTRY)


def build_strategy(name: str, params: Dict[str, Any] | None = None) -> "Strategy":
    if name not in _REGISTRY:
        raise KeyError(f"Unknown strategy {name!r}. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[name](params or {})


class Strategy(ABC):
    #: Set by @register.
    name: str = "base"
    #: Whether this is a mean-reversion strategy. For memecoins these are more
    #: dangerous (trends run brutally or collapse) — the scorer down-weights them.
    mean_reversion: bool = False
    #: Default parameters; overridden by config.
    defaults: Dict[str, Any] = {}

    def __init__(self, params: Dict[str, Any] | None = None):
        self.params: Dict[str, Any] = {**self.defaults, **(params or {})}

    def p(self, key: str) -> Any:
        return self.params[key]

    @property
    def warmup(self) -> int:
        """Bars needed before the strategy can produce a valid signal."""
        return int(self.params.get("warmup", 200))

    @abstractmethod
    def generate(self, df: pd.DataFrame) -> Signal:
        """Return a Signal from the *last closed* bar of ``df``.

        ``df`` contains only closed candles (see core.utils.closed_bars).
        Implementations must not peek beyond ``df.iloc[-1]``.
        """
        raise NotImplementedError

    # Helpers ---------------------------------------------------------------
    @staticmethod
    def _none() -> Signal:
        return Signal(SignalType.NONE)

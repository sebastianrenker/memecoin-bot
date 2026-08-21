"""Core data types shared across the framework.

All monetary values are simulated ("paper money"). Nothing here touches a real
exchange account. See execution/live.py — live trading is a locked stub.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class SignalType(str, Enum):
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT = "exit"
    NONE = "none"


@dataclass(frozen=True)
class Signal:
    """A trading intention produced on a *closed* bar.

    The engine acts on it at the OPEN of the following bar (no look-ahead).
    ``atr`` is the stop distance basis (absolute price units) computed on
    closed candles only.
    """
    type: SignalType
    atr: float = 0.0
    confidence: float = 1.0  # 0..1, used to scale position size
    reason: str = ""


@dataclass
class Position:
    strategy: str
    symbol: str
    side: Side
    qty: float
    entry_price: float
    stop_price: float
    take_profit: Optional[float]
    entry_index: int
    notional: float
    risk_amount: float
    opened_ts: Optional[int] = None
    meta: dict = field(default_factory=dict)


@dataclass
class Trade:
    strategy: str
    symbol: str
    side: Side
    qty: float
    entry_price: float
    exit_price: float
    entry_index: int
    exit_index: int
    pnl: float            # net of fees/slippage, in quote currency
    r_multiple: float     # pnl / risk_amount
    fees: float
    reason: str           # "stop" | "take_profit" | "signal_exit" | "eod"
    entry_ts: Optional[int] = None
    exit_ts: Optional[int] = None


@dataclass
class EquityPoint:
    index: int
    ts: Optional[int]
    equity: float

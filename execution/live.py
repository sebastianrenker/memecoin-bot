"""LOCKED live-trading adapter.

This project is a learning / analysis tool that trades SIMULATED money only.
Live trading is intentionally not implemented. Every entry point raises
``LiveTradingNotEnabled``. There is no flag, config value, or environment
variable that turns this into a real-money trader — by design.
"""
from __future__ import annotations


class LiveTradingNotEnabled(RuntimeError):
    """Raised on any attempt to use the live adapter. Live trading is disabled."""


_MSG = (
    "Live trading is disabled. This is a paper-only analysis tool. "
    "It will not place real orders. If you want real trading you must build and "
    "own that yourself — understanding that memecoins overwhelmingly go to zero."
)


class LiveBroker:
    def __init__(self, *args, **kwargs):
        raise LiveTradingNotEnabled(_MSG)

    def create_order(self, *args, **kwargs):
        raise LiveTradingNotEnabled(_MSG)

    def cancel_order(self, *args, **kwargs):
        raise LiveTradingNotEnabled(_MSG)

    def fetch_balance(self, *args, **kwargs):
        raise LiveTradingNotEnabled(_MSG)

"""Risk management for the paper trader.

Encodes the mandatory limits and the hard-won fixes:
  * Max risk per trade is enforced by the engine sizing; here we cap the number
    of simultaneously open positions and hold at most one position per
    (strategy, symbol).
  * Minimum stop distance: stops tighter than ``min_stop_frac * price`` are
    REJECTED (never widened) — prevents the ATR≈0 stop-loss loop.
  * Bar debounce: after a stop/TP exit on a bar, the same (strategy, symbol)
    may not reopen on that same bar.
  * Daily-loss circuit breaker: a *safe hold*. When tripped, no new orders are
    placed but the loop keeps ticking. The trip persists and auto-resets only
    on a new UTC day. It does NOT terminate the process.
  * Total-drawdown kill switch: trips on peak-to-trough drawdown and requires a
    manual reset (more severe than the daily breaker).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class RiskConfig:
    max_open_positions: int = 5
    daily_loss_limit: float = 0.03
    max_drawdown_kill: float = 0.25
    min_stop_frac: float = 0.005


def _utc_date(ts: Optional[float]) -> _dt.date:
    if ts is None:
        return _dt.datetime.now(_dt.timezone.utc).date()
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).date()


@dataclass
class RiskManager:
    cfg: RiskConfig
    peak_equity: float = 0.0
    day: Optional[_dt.date] = None
    day_start_equity: float = 0.0
    breaker_tripped: bool = False
    kill_tripped: bool = False
    open_keys: Dict[Tuple[str, str], bool] = field(default_factory=dict)
    last_exit_bar: Dict[Tuple[str, str], int] = field(default_factory=dict)

    def init_equity(self, equity: float, ts: Optional[float] = None) -> None:
        self.peak_equity = max(self.peak_equity, equity)
        if self.day is None:
            self.day = _utc_date(ts)
            self.day_start_equity = equity

    # ---- equity-driven state -------------------------------------------
    def on_equity(self, equity: float, ts: Optional[float] = None) -> None:
        """Update peak, roll the UTC day, and evaluate breaker + kill switch."""
        if self.day is None:
            self.init_equity(equity, ts)

        today = _utc_date(ts)
        if today != self.day:
            # New UTC day: reset the daily breaker and re-baseline daily equity.
            self.day = today
            self.day_start_equity = equity
            self.breaker_tripped = False  # daily breaker auto-resets; kill switch does not

        self.peak_equity = max(self.peak_equity, equity)

        # Total-drawdown kill switch (manual reset only).
        if self.peak_equity > 0:
            dd = (self.peak_equity - equity) / self.peak_equity
            if dd >= self.cfg.max_drawdown_kill:
                self.kill_tripped = True

        # Daily-loss circuit breaker (safe hold; auto-reset next UTC day).
        if self.day_start_equity > 0:
            day_loss = (self.day_start_equity - equity) / self.day_start_equity
            if day_loss >= self.cfg.daily_loss_limit:
                self.breaker_tripped = True

    # ---- gate for new orders -------------------------------------------
    def can_open(self, strategy: str, symbol: str, price: float, stop_distance: float,
                 bar_id: int) -> Tuple[bool, str]:
        if self.kill_tripped:
            return False, "kill_switch: total-drawdown kill switch active (manual reset required)"
        if self.breaker_tripped:
            return False, "circuit_breaker: daily-loss breaker active (safe hold until new UTC day)"
        key = (strategy, symbol)
        if key in self.open_keys:
            return False, "position already open for this (strategy, symbol)"
        if len(self.open_keys) >= self.cfg.max_open_positions:
            return False, f"max_open_positions ({self.cfg.max_open_positions}) reached"
        if stop_distance <= 0 or stop_distance < self.cfg.min_stop_frac * price:
            return False, "stop too tight (rejected, not widened) — min_stop_frac guard"
        if self.last_exit_bar.get(key) == bar_id:
            return False, "bar debounce: already exited this (strategy, symbol) on this bar"
        return True, "ok"

    def register_open(self, strategy: str, symbol: str) -> None:
        self.open_keys[(strategy, symbol)] = True

    def register_close(self, strategy: str, symbol: str, bar_id: int) -> None:
        key = (strategy, symbol)
        self.open_keys.pop(key, None)
        self.last_exit_bar[key] = bar_id

    # ---- manual controls -----------------------------------------------
    def reset_breaker(self) -> None:
        self.breaker_tripped = False

    def reset_kill(self) -> None:
        self.kill_tripped = False

    @property
    def halted(self) -> bool:
        return self.kill_tripped or self.breaker_tripped

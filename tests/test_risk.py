"""Regression tests for the mandatory risk fixes."""
from __future__ import annotations

import datetime as dt

from risk.manager import RiskConfig, RiskManager


def _rm(**kw):
    cfg = RiskConfig(**kw)
    return RiskManager(cfg=cfg)


def test_min_stop_distance_rejected_not_widened():
    rm = _rm(min_stop_frac=0.005)
    rm.init_equity(10_000)
    ok, reason = rm.can_open("s", "PEPE/USDT", price=100.0, stop_distance=0.1, bar_id=1)
    assert not ok and "min_stop_frac" in reason
    ok2, _ = rm.can_open("s", "PEPE/USDT", price=100.0, stop_distance=0.6, bar_id=1)
    assert ok2


def test_bar_debounce_blocks_same_bar_reentry():
    rm = _rm()
    rm.init_equity(10_000)
    rm.register_open("s", "DOGE/USDT")
    rm.register_close("s", "DOGE/USDT", bar_id=42)
    ok, reason = rm.can_open("s", "DOGE/USDT", price=1.0, stop_distance=0.1, bar_id=42)
    assert not ok and "debounce" in reason
    ok2, _ = rm.can_open("s", "DOGE/USDT", price=1.0, stop_distance=0.1, bar_id=43)
    assert ok2  # next bar is fine


def test_one_position_per_strategy_symbol():
    rm = _rm()
    rm.init_equity(10_000)
    rm.register_open("s", "WIF/USDT")
    ok, reason = rm.can_open("s", "WIF/USDT", price=1.0, stop_distance=0.1, bar_id=1)
    assert not ok and "already open" in reason


def test_max_open_positions():
    rm = _rm(max_open_positions=2)
    rm.init_equity(10_000)
    rm.register_open("s", "A/USDT")
    rm.register_open("s", "B/USDT")
    ok, reason = rm.can_open("s", "C/USDT", price=1.0, stop_distance=0.1, bar_id=1)
    assert not ok and "max_open_positions" in reason


def test_daily_breaker_is_safe_hold_and_auto_resets_next_utc_day():
    rm = _rm(daily_loss_limit=0.03)
    t0 = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc).timestamp()
    rm.init_equity(10_000, ts=t0)
    # Lose 4% same day -> breaker trips (safe hold, NOT process exit).
    rm.on_equity(9_600, ts=t0 + 3600)
    assert rm.breaker_tripped
    ok, reason = rm.can_open("s", "A/USDT", price=1.0, stop_distance=0.1, bar_id=1)
    assert not ok and "circuit_breaker" in reason
    # Next UTC day -> auto reset.
    t1 = dt.datetime(2026, 1, 2, 0, 5, tzinfo=dt.timezone.utc).timestamp()
    rm.on_equity(9_600, ts=t1)
    assert not rm.breaker_tripped
    ok2, _ = rm.can_open("s", "A/USDT", price=1.0, stop_distance=0.1, bar_id=1)
    assert ok2


def test_drawdown_kill_switch_requires_manual_reset():
    rm = _rm(max_drawdown_kill=0.25, daily_loss_limit=0.99)
    t0 = dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    rm.init_equity(10_000, ts=t0)
    rm.on_equity(12_000, ts=t0 + 3600)      # new peak
    rm.on_equity(8_000, ts=t0 + 7200)       # -33% from peak -> kill
    assert rm.kill_tripped
    # A new UTC day must NOT clear the kill switch.
    t1 = dt.datetime(2026, 1, 3, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    rm.on_equity(8_000, ts=t1)
    assert rm.kill_tripped
    rm.reset_kill()
    assert not rm.kill_tripped

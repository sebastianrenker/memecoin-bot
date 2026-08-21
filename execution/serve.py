"""Long-running paper-trading service.

  * Double-start protection via a lock file + fresh heartbeat check.
  * Main loop ticks the PaperTrader on the configured interval.
  * A daemon "adjustment" thread periodically re-evaluates combos and writes
    evaluations. It uses its OWN Database connection (SQLite connections are not
    shared across threads).
  * A tripped circuit breaker does NOT stop the process — the loop keeps ticking
    in safe-hold until the breaker auto-resets on a new UTC day or is reset via
    the control table.
"""
from __future__ import annotations

import os
import threading
import time
from typing import List, Optional

from backtest.evaluation import evaluate_combo
from config.settings import Settings, build_engine_config
from data.base import DataUnavailable
from execution.paper import Combo, PaperTrader
from persistence.db import Database


class AlreadyRunning(RuntimeError):
    pass


def _lock_path(db_path: str) -> str:
    return db_path + ".lock"


def _acquire_lock(db_path: str, db: Database, stale_sec: float = 300.0) -> None:
    lp = _lock_path(db_path)
    if os.path.exists(lp):
        # Consider stale if heartbeat is old.
        row = db.conn.execute("SELECT ts FROM heartbeat WHERE id=1").fetchone()
        fresh = row and (time.time() * 1000 - row["ts"]) < stale_sec * 1000
        if fresh:
            raise AlreadyRunning(f"serve already running (lock {lp}, fresh heartbeat)")
    with open(lp, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))


def _release_lock(db_path: str) -> None:
    try:
        os.remove(_lock_path(db_path))
    except OSError:
        pass


def _adjustment_loop(settings: Settings, db_path: str, combos: List[Combo],
                     stop: threading.Event, interval_sec: float) -> None:
    """Re-evaluate combos periodically. Own DB connection (thread safety)."""
    from data.factory import build_data_source
    db = Database(db_path)                 # separate connection for this thread
    data = build_data_source(settings)
    cfg = build_engine_config(settings)
    tf = settings.get("data.timeframe", "1h")
    lookback = int(settings.get("data.lookback_days", 180))
    try:
        while not stop.is_set():
            for c in combos:
                if stop.is_set():
                    break
                try:
                    raw = data.fetch_ohlcv(c.symbol, tf, lookback)
                except DataUnavailable as e:
                    db.audit("warn", "eval_skip", f"{c.symbol}: {e}")
                    continue
                ev = evaluate_combo(c.strategy, c.symbol, raw, cfg, settings, tf)
                if ev is not None:
                    db.record_evaluation({"ts": int(time.time() * 1000), **ev.as_record()})
            stop.wait(interval_sec)
    finally:
        db.close()


def serve(settings: Settings, combos: List[Combo], db_path: str,
          tick_interval_sec: float = 60.0, adjust_interval_sec: float = 1800.0,
          max_ticks: Optional[int] = None, enable_adjust: bool = True) -> None:
    from data.factory import build_data_source

    db = Database(db_path)
    _acquire_lock(db_path, db)
    db.set_control("command", "run")
    db.audit("info", "serve_start", f"combos={len(combos)} tick={tick_interval_sec}s")

    data = build_data_source(settings)
    trader = PaperTrader(settings, data, db, combos)
    trader.recover_state()

    stop = threading.Event()
    if enable_adjust:
        adj = threading.Thread(target=_adjustment_loop,
                               args=(settings, db_path, combos, stop, adjust_interval_sec),
                               daemon=True)
        adj.start()

    ticks = 0
    try:
        while True:
            if db.get_control("command", "run") == "stop":
                db.audit("info", "serve_stop", "control command=stop")
                break
            trader.tick()
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            stop.wait(tick_interval_sec)
    except KeyboardInterrupt:
        db.audit("info", "serve_interrupt", "KeyboardInterrupt")
    finally:
        stop.set()
        db.checkpoint()
        db.audit("info", "serve_end", f"ticks={ticks}")
        _release_lock(db_path)
        db.close()

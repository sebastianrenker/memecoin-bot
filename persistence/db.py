"""SQLite persistence (WAL + busy_timeout).

Tables: evaluations, trades, audit_log, equity_points, positions_snapshot,
heartbeat, control.

Threading rule: SQLite connections are NOT shared across threads. Each thread
(e.g. the serve loop and the adjustment thread) must create its OWN Database
instance pointing at the same file. WAL mode lets them read/write concurrently.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER, strategy TEXT, symbol TEXT, score REAL, light TEXT,
    expectancy_r REAL, n_trades INTEGER, mean_efficiency REAL, ruin_prob REAL,
    extra TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_open INTEGER, ts_close INTEGER, strategy TEXT, symbol TEXT, side TEXT,
    qty REAL, entry REAL, exit REAL, pnl REAL, r_multiple REAL, fees REAL, reason TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER, level TEXT, event TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS equity_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER, equity REAL
);
CREATE TABLE IF NOT EXISTS positions_snapshot (
    strategy TEXT, symbol TEXT, side TEXT, qty REAL, entry REAL, stop REAL,
    tp REAL, opened_ts INTEGER, risk REAL, entry_fee REAL,
    PRIMARY KEY (strategy, symbol)
);
CREATE TABLE IF NOT EXISTS heartbeat (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ts INTEGER, status TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS control (
    key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY, value TEXT
);
"""


class Database:
    def __init__(self, path: str, timeout: float = 30.0):
        self.path = path
        self.conn = sqlite3.connect(path, timeout=timeout)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=30000;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # ---- lifecycle -------------------------------------------------------
    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def checkpoint(self) -> None:
        """Fold the WAL back into the main db file (used before committing state)."""
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            self.conn.commit()
        except Exception:
            pass

    # ---- writes ----------------------------------------------------------
    def audit(self, level: str, event: str, detail: str = "", ts: Optional[int] = None) -> None:
        self.conn.execute("INSERT INTO audit_log(ts, level, event, detail) VALUES (?,?,?,?)",
                          (ts or int(time.time() * 1000), level, event, detail))
        self.conn.commit()

    def record_trade(self, t: Dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO trades(ts_open, ts_close, strategy, symbol, side, qty, entry,
               exit, pnl, r_multiple, fees, reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t.get("ts_open"), t.get("ts_close"), t["strategy"], t["symbol"], t["side"],
             t["qty"], t["entry"], t["exit"], t["pnl"], t["r_multiple"], t["fees"], t["reason"]))
        self.conn.commit()

    def record_equity(self, equity: float, ts: Optional[int] = None) -> None:
        self.conn.execute("INSERT INTO equity_points(ts, equity) VALUES (?,?)",
                          (ts or int(time.time() * 1000), equity))
        self.conn.commit()

    def record_evaluation(self, ev: Dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO evaluations(ts, strategy, symbol, score, light, expectancy_r,
               n_trades, mean_efficiency, ruin_prob, extra) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (ev.get("ts", int(time.time() * 1000)), ev["strategy"], ev["symbol"],
             ev.get("score"), ev.get("light"), ev.get("expectancy_r"), ev.get("n_trades"),
             ev.get("mean_efficiency"), ev.get("ruin_prob"), json.dumps(ev.get("extra", {}))))
        self.conn.commit()

    def heartbeat(self, status: str, detail: str = "", ts: Optional[int] = None) -> None:
        self.conn.execute(
            "INSERT INTO heartbeat(id, ts, status, detail) VALUES (1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET ts=excluded.ts, status=excluded.status, detail=excluded.detail",
            (ts or int(time.time() * 1000), status, detail))
        self.conn.commit()

    def snapshot_positions(self, positions: List[Dict[str, Any]]) -> None:
        self.conn.execute("DELETE FROM positions_snapshot")
        for p in positions:
            self.conn.execute(
                """INSERT INTO positions_snapshot(strategy, symbol, side, qty, entry, stop,
                   tp, opened_ts, risk, entry_fee) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (p["strategy"], p["symbol"], p["side"], p["qty"], p["entry"], p["stop"],
                 p.get("tp"), p.get("opened_ts"), p.get("risk"), p.get("entry_fee")))
        self.conn.commit()

    # ---- control / meta --------------------------------------------------
    def set_control(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO control(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()

    def get_control(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM control WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()

    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    # ---- reads / recovery ------------------------------------------------
    def last_equity(self) -> Optional[float]:
        row = self.conn.execute("SELECT equity FROM equity_points ORDER BY id DESC LIMIT 1").fetchone()
        return float(row["equity"]) if row else None

    def load_positions(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM positions_snapshot").fetchall()
        return [dict(r) for r in rows]

    def recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def equity_curve(self, limit: int = 5000) -> List[Tuple[int, float]]:
        rows = self.conn.execute(
            "SELECT ts, equity FROM equity_points ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [(int(r["ts"]), float(r["equity"])) for r in reversed(rows)]

    def latest_evaluations(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM evaluations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def recent_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

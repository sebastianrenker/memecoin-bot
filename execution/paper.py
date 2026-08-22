"""Paper trader — simulated execution over real closed candles.

One ``tick()`` processes the latest CLOSED bar for every active
(strategy, symbol) combination: it manages open positions (stop before TP, or a
signal exit) and, when flat and the risk gate allows, opens a new simulated
position at the current price. State (cash, positions, breaker/kill flags) is
persisted so a restart resumes exactly where it left off.

Simulated money only. No real orders are ever placed (see execution/live.py).
"""
from __future__ import annotations

import datetime as _dt
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.settings import Settings, build_engine_config, build_risk_config
from core.types import Side
from core.utils import closed_bars, timeframe_ms
from data.base import DataUnavailable
from persistence.db import Database
from risk.manager import RiskManager
from strategies.base import build_strategy


@dataclass
class Combo:
    strategy: str
    symbol: str
    params: Dict[str, Any]

    @property
    def key(self) -> Tuple[str, str]:
        return (self.strategy, self.symbol)


class PaperTrader:
    def __init__(self, settings: Settings, data_source, db: Database, combos: List[Combo]):
        self.s = settings
        self.data = data_source
        self.db = db
        self.combos = combos
        self.cfg = build_engine_config(settings)
        self.risk = RiskManager(build_risk_config(settings))
        self.timeframe = settings.get("data.timeframe", "1h")
        self.lookback_days = int(settings.get("data.lookback_days", 180))
        self.require_real = bool(settings.get("data.require_real", True))
        self.cash = self.cfg.initial_equity
        self.positions: Dict[Tuple[str, str], dict] = {}

    # ---- state recovery --------------------------------------------------
    def recover_state(self) -> None:
        cash = self.db.get_meta("cash")
        self.cash = float(cash) if cash is not None else self.cfg.initial_equity
        for p in self.db.load_positions():
            key = (p["strategy"], p["symbol"])
            self.positions[key] = dict(
                side=Side(p["side"]), qty=float(p["qty"]), entry=float(p["entry"]),
                stop=float(p["stop"]), tp=(float(p["tp"]) if p["tp"] is not None else None),
                risk=float(p["risk"]) if p["risk"] is not None else 0.0,
                entry_fee=float(p["entry_fee"]) if p["entry_fee"] is not None else 0.0,
                opened_ts=p.get("opened_ts"), entry_index=0)
            self.risk.register_open(*key)

        peak = self.db.get_meta("peak_equity")
        self.risk.peak_equity = float(peak) if peak else self.cash
        dse = self.db.get_meta("day_start_equity")
        self.risk.day_start_equity = float(dse) if dse else self.cash
        day = self.db.get_meta("day")
        self.risk.day = _dt.date.fromisoformat(day) if day else _dt.datetime.now(_dt.timezone.utc).date()
        self.risk.breaker_tripped = self.db.get_control("breaker_tripped", "0") == "1"
        self.risk.kill_tripped = self.db.get_control("kill_tripped", "0") == "1"
        self.db.audit("info", "recover_state",
                      f"cash={self.cash:.2f} positions={len(self.positions)} "
                      f"breaker={self.risk.breaker_tripped} kill={self.risk.kill_tripped}")

    # ---- helpers ---------------------------------------------------------
    def _fetch_closed(self, symbol: str, now_ms: int) -> Optional[pd.DataFrame]:
        try:
            raw = self.data.fetch_ohlcv(symbol, self.timeframe, self.lookback_days)
        except DataUnavailable as e:
            self.db.audit("warn", "data_skip", f"{symbol}: {e}")
            return None
        df = closed_bars(raw, self.timeframe, now_ms)
        if df is None or len(df) < 5:
            self.db.audit("warn", "data_skip", f"{symbol}: too few closed bars")
            return None
        df.attrs["symbol"] = symbol
        return df

    def _open(self, combo: Combo, price: float, atr: float, confidence: float,
              bar_ts: int) -> None:
        cfg = self.cfg
        slip = cfg.eff_slip
        fill = price * (1 + slip)  # long-only default; entry at current price
        conf = max(0.0, min(1.0, confidence))
        risk_amount = self.cash * cfg.risk_per_trade * conf
        if risk_amount <= 0 or atr <= 0:
            return
        qty = risk_amount / atr
        notional = qty * fill
        max_notional = self.cash * cfg.leverage_cap
        if notional > max_notional and notional > 0:
            qty *= max_notional / notional
            notional = qty * fill
        if qty <= 0:
            return
        entry_fee = notional * cfg.eff_fee
        self.cash -= entry_fee
        pos = dict(side=Side.LONG, qty=qty, entry=fill, stop=fill - atr,
                   tp=(fill + cfg.take_profit_r * atr if cfg.take_profit_r else None),
                   risk=qty * atr, entry_fee=entry_fee, opened_ts=bar_ts, entry_index=0)
        self.positions[combo.key] = pos
        self.risk.register_open(*combo.key)
        self.db.audit("info", "open", f"{combo.strategy}@{combo.symbol} qty={qty:.4g} "
                                      f"entry={fill:.6g} stop={pos['stop']:.6g}")

    def _close(self, combo: Combo, exit_price: float, bar_ts: int, reason: str) -> None:
        cfg = self.cfg
        pos = self.positions.pop(combo.key)
        exit_notional = pos["qty"] * exit_price
        exit_fee = exit_notional * cfg.eff_fee
        gross = pos["qty"] * (exit_price - pos["entry"])  # long-only
        pnl = gross - exit_fee - pos["entry_fee"]
        self.cash += gross - exit_fee
        r_mult = pnl / pos["risk"] if pos["risk"] > 0 else 0.0
        self.db.record_trade(dict(
            ts_open=pos.get("opened_ts"), ts_close=bar_ts, strategy=combo.strategy,
            symbol=combo.symbol, side=pos["side"].value, qty=pos["qty"], entry=pos["entry"],
            exit=exit_price, pnl=pnl, r_multiple=r_mult, fees=pos["entry_fee"] + exit_fee,
            reason=reason))
        self.risk.register_close(combo.strategy, combo.symbol, bar_ts)
        self.db.audit("info", "close", f"{combo.strategy}@{combo.symbol} pnl={pnl:.2f} "
                                      f"R={r_mult:.2f} reason={reason}")

    # ---- one tick --------------------------------------------------------
    def tick(self, now_ms: Optional[int] = None) -> Dict[str, Any]:
        now_ms = now_ms or int(time.time() * 1000)
        cmd = self.db.get_control("command", "run")
        if cmd == "stop":
            self.db.heartbeat("stopped", "control command=stop")
            return {"status": "stopped"}
        if self.db.get_control("reset_breaker", "0") == "1":
            self.risk.reset_breaker()
            self.db.set_control("reset_breaker", "0")
            self.db.audit("info", "reset_breaker", "manual reset")

        processed, skipped = 0, 0
        last_prices: Dict[Tuple[str, str], float] = {}
        df_by_symbol: Dict[str, Optional[pd.DataFrame]] = {}  # fetch each symbol once per tick

        for combo in self.combos:
            if combo.symbol not in df_by_symbol:
                df_by_symbol[combo.symbol] = self._fetch_closed(combo.symbol, now_ms)
            df = df_by_symbol[combo.symbol]
            if df is None:
                skipped += 1
                continue
            processed += 1
            price = float(df["close"].iloc[-1])
            hi = float(df["high"].iloc[-1])
            lo = float(df["low"].iloc[-1])
            bar_ts = int(df["timestamp"].iloc[-1])
            last_prices[combo.key] = price
            strat = build_strategy(combo.strategy, combo.params)

            if combo.key in self.positions:
                pos = self.positions[combo.key]
                slip = self.cfg.eff_slip
                # Stop BEFORE take-profit.
                if lo <= pos["stop"]:
                    self._close(combo, pos["stop"] * (1 - slip), bar_ts, "stop")
                elif pos["tp"] is not None and hi >= pos["tp"]:
                    self._close(combo, pos["tp"] * (1 - slip), bar_ts, "take_profit")
                else:
                    sig = strat.generate(df)
                    if sig.type.value == "exit":
                        self._close(combo, price * (1 - slip), bar_ts, "signal_exit")
            elif cmd == "run":
                sig = strat.generate(df)
                if sig.type.value == "enter_long":
                    ok, reason = self.risk.can_open(combo.strategy, combo.symbol, price,
                                                    float(sig.atr), bar_ts)
                    if ok:
                        self._open(combo, price, float(sig.atr), float(sig.confidence), bar_ts)
                    else:
                        self.db.audit("info", "no_open", f"{combo.strategy}@{combo.symbol}: {reason}")

        # Mark-to-market equity and risk update.
        equity = self.cash
        for key, pos in self.positions.items():
            px = last_prices.get(key, pos["entry"])
            equity += pos["qty"] * (px - pos["entry"])
        self.risk.on_equity(equity, ts=now_ms / 1000.0)

        self._persist(equity, now_ms, processed, skipped)
        return {"status": "safe_hold" if self.risk.halted else "running",
                "equity": equity, "cash": self.cash, "open_positions": len(self.positions),
                "processed": processed, "skipped": skipped,
                "breaker": self.risk.breaker_tripped, "kill": self.risk.kill_tripped}

    def _persist(self, equity: float, now_ms: int, processed: int, skipped: int) -> None:
        self.db.record_equity(equity, now_ms)
        self.db.snapshot_positions([
            dict(strategy=k[0], symbol=k[1], side=p["side"].value, qty=p["qty"],
                 entry=p["entry"], stop=p["stop"], tp=p["tp"], opened_ts=p.get("opened_ts"),
                 risk=p["risk"], entry_fee=p["entry_fee"])
            for k, p in self.positions.items()])
        if self.db.get_meta("initial_equity") is None:
            self.db.set_meta("initial_equity", f"{self.cfg.initial_equity}")
        self.db.set_meta("cash", f"{self.cash}")
        self.db.set_meta("peak_equity", f"{self.risk.peak_equity}")
        self.db.set_meta("day_start_equity", f"{self.risk.day_start_equity}")
        self.db.set_meta("day", self.risk.day.isoformat() if self.risk.day else "")
        self.db.set_control("breaker_tripped", "1" if self.risk.breaker_tripped else "0")
        self.db.set_control("kill_tripped", "1" if self.risk.kill_tripped else "0")
        status = "safe_hold" if self.risk.halted else "running"
        self.db.heartbeat(status, f"eq={equity:.2f} cash={self.cash:.2f} "
                                  f"open={len(self.positions)} proc={processed} skip={skipped}")

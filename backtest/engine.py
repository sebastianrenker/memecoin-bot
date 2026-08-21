"""Event-based backtest engine — single strategy, single symbol.

Correctness rules (enforced and covered by tests):
  * A signal decided on the close of bar ``t`` is executed at the OPEN of bar
    ``t+1``. No look-ahead: the strategy only ever sees ``df.iloc[:t+1]``.
  * Within a bar the STOP is checked before the TAKE-PROFIT (pessimistic).
  * Fees and slippage are charged per side.
  * Position size = risk_per_trade * equity * confidence / stop_distance.
  * Leverage is capped AND the entry fee is charged on the capped quantity —
    the notional is recomputed after the cap.
  * Stops tighter than ``min_stop_frac * price`` are REJECTED, never widened
    (prevents the ATR≈0 stop-loss loop).
  * A new position is not opened on the same bar a position was just closed
    (bar debounce).
  * The input df must already be restricted to closed candles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from core.types import EquityPoint, Side, Signal, SignalType, Trade
from strategies.base import Strategy


@dataclass
class EngineConfig:
    initial_equity: float = 10_000.0
    fee_rate: float = 0.001          # per side; memecoins are higher, set in config
    slippage_rate: float = 0.0015    # per side
    risk_per_trade: float = 0.01     # 1% of equity risked at the stop
    leverage_cap: float = 1.0        # notional <= leverage_cap * equity
    min_stop_frac: float = 0.0025    # reject stops tighter than 0.25% of price
    take_profit_r: Optional[float] = 2.0  # TP at entry +/- r*stop; None disables
    allow_short: bool = True
    cost_multiplier: float = 1.0     # pessimistic robustness: 2.0 doubles costs

    @property
    def eff_fee(self) -> float:
        return self.fee_rate * self.cost_multiplier

    @property
    def eff_slip(self) -> float:
        return self.slippage_rate * self.cost_multiplier


@dataclass
class BacktestResult:
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[EquityPoint] = field(default_factory=list)
    rejected_tight_stops: int = 0
    final_equity: float = 0.0
    config: Optional[EngineConfig] = None

    @property
    def r_multiples(self) -> List[float]:
        return [t.r_multiple for t in self.trades]


def _ts_at(df: pd.DataFrame, i: int) -> Optional[int]:
    if "timestamp" in df.columns:
        return int(df["timestamp"].iloc[i])
    try:
        return int(df.index[i])
    except (ValueError, TypeError):
        return None


def run_backtest(strategy: Strategy, df: pd.DataFrame, cfg: EngineConfig) -> BacktestResult:
    res = BacktestResult(config=cfg)
    n = len(df)
    if n == 0:
        res.final_equity = cfg.initial_equity
        return res

    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    cash = cfg.initial_equity
    pos: Optional[dict] = None
    pending_entry: Optional[Signal] = None
    pending_exit = False
    last_exit_bar = -1

    def open_position(sig: Signal, bar: int) -> None:
        nonlocal cash, pos
        want_long = sig.type == SignalType.ENTER_LONG
        want_short = sig.type == SignalType.ENTER_SHORT and cfg.allow_short
        if not (want_long or want_short):
            return
        side = Side.LONG if want_long else Side.SHORT
        stop_dist = float(sig.atr)
        open_px = float(o[bar])
        if stop_dist <= 0 or stop_dist < cfg.min_stop_frac * open_px:
            res.rejected_tight_stops += 1
            return
        slip = cfg.eff_slip
        fill = open_px * (1 + slip) if side == Side.LONG else open_px * (1 - slip)
        conf = max(0.0, min(1.0, float(sig.confidence)))
        risk_amount = cash * cfg.risk_per_trade * conf
        if risk_amount <= 0:
            return
        qty = risk_amount / stop_dist
        notional = qty * fill
        max_notional = cash * cfg.leverage_cap
        if notional > max_notional and notional > 0:
            qty *= max_notional / notional
            notional = qty * fill
        if qty <= 0:
            return
        entry_fee = notional * cfg.eff_fee
        cash -= entry_fee
        if side == Side.LONG:
            stop_price = fill - stop_dist
            tp = fill + cfg.take_profit_r * stop_dist if cfg.take_profit_r else None
        else:
            stop_price = fill + stop_dist
            tp = fill - cfg.take_profit_r * stop_dist if cfg.take_profit_r else None
        pos = dict(side=side, qty=qty, entry=fill, stop=stop_price, tp=tp,
                   entry_index=bar, risk=qty * stop_dist, entry_fee=entry_fee,
                   entry_ts=_ts_at(df, bar))

    def close_position(exit_px: float, bar: int, reason: str) -> None:
        nonlocal cash, pos, last_exit_bar
        assert pos is not None
        slip = cfg.eff_slip
        if reason in ("signal_exit",):
            # exit at open with slippage against us
            exit_px = exit_px * (1 - slip) if pos["side"] == Side.LONG else exit_px * (1 + slip)
        exit_notional = pos["qty"] * exit_px
        exit_fee = exit_notional * cfg.eff_fee
        if pos["side"] == Side.LONG:
            gross = pos["qty"] * (exit_px - pos["entry"])
        else:
            gross = pos["qty"] * (pos["entry"] - exit_px)
        pnl = gross - exit_fee - pos["entry_fee"]
        cash += gross - exit_fee
        r_mult = pnl / pos["risk"] if pos["risk"] > 0 else 0.0
        res.trades.append(Trade(
            strategy=strategy.name, symbol=str(df.attrs.get("symbol", "?")),
            side=pos["side"], qty=pos["qty"], entry_price=pos["entry"], exit_price=exit_px,
            entry_index=pos["entry_index"], exit_index=bar, pnl=pnl, r_multiple=r_mult,
            fees=pos["entry_fee"] + exit_fee, reason=reason,
            entry_ts=pos["entry_ts"], exit_ts=_ts_at(df, bar)))
        last_exit_bar = bar
        pos = None

    for i in range(n):
        open_px = float(o[i])

        # 1) Execute pending decisions from the previous closed bar at this open.
        if pending_exit and pos is not None:
            close_position(open_px, i, "signal_exit")
        if pending_entry is not None and pos is None and i != last_exit_bar:
            open_position(pending_entry, i)
        pending_entry = None
        pending_exit = False

        # 2) Intra-bar stop/TP management (stop BEFORE take-profit).
        if pos is not None:
            slip = cfg.eff_slip
            if pos["side"] == Side.LONG:
                if l[i] <= pos["stop"]:
                    close_position(pos["stop"] * (1 - slip), i, "stop")
                elif pos["tp"] is not None and h[i] >= pos["tp"]:
                    close_position(pos["tp"] * (1 - slip), i, "take_profit")
            else:
                if h[i] >= pos["stop"]:
                    close_position(pos["stop"] * (1 + slip), i, "stop")
                elif pos["tp"] is not None and l[i] <= pos["tp"]:
                    close_position(pos["tp"] * (1 + slip), i, "take_profit")

        # 3) Mark-to-market equity at the close of this bar.
        mtm = cash
        if pos is not None:
            if pos["side"] == Side.LONG:
                mtm += pos["qty"] * (float(c[i]) - pos["entry"])
            else:
                mtm += pos["qty"] * (pos["entry"] - float(c[i]))
        res.equity_curve.append(EquityPoint(i, _ts_at(df, i), mtm))

        # 4) Decide a signal on THIS closed bar for the next open.
        if i >= strategy.warmup and i < n - 1:
            sig = strategy.generate(df.iloc[: i + 1])
            if pos is None and sig.type in (SignalType.ENTER_LONG, SignalType.ENTER_SHORT):
                pending_entry = sig
            elif pos is not None and sig.type == SignalType.EXIT:
                pending_exit = True

    res.final_equity = res.equity_curve[-1].equity if res.equity_curve else cfg.initial_equity
    return res

"""Paper-trader lifecycle: open, stop-out, breaker safe-hold, restart recovery."""
from __future__ import annotations

import pandas as pd

from config.settings import Settings
from core.types import Signal, SignalType
from execution.paper import Combo, PaperTrader
from persistence.db import Database
from strategies.base import Strategy, register
from tests.synth import make_df

TF_MS = 3_600_000


@register("paper_always_enter")
class _AlwaysEnter(Strategy):
    defaults = {"atr": 5.0}

    @property
    def warmup(self):
        return 1

    def generate(self, df: pd.DataFrame) -> Signal:
        return Signal(SignalType.ENTER_LONG, atr=float(self.p("atr")))


class _FakeSource:
    """Returns queued frames; raises if exhausted."""
    def __init__(self, frames):
        self.frames = list(frames)
        self.i = 0

    def fetch_ohlcv(self, symbol, timeframe, lookback_days):
        f = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return f


def _settings():
    s = Settings.load()
    # Deterministic, cheap costs for assertions.
    s.raw["engine"]["cost_multiplier"] = 1.0
    s.raw["engine"]["slippage_rate"] = 0.0
    s.raw["engine"]["fee_rate"] = 0.0
    return s


def _frame(prices, last_low=None):
    df = make_df(prices, timeframe_ms=TF_MS)
    if last_low is not None:
        df.loc[df.index[-1], "low"] = last_low
    return df


def test_open_then_stop_out(tmp_path):
    s = _settings()
    db = Database(str(tmp_path / "p.db"))
    combos = [Combo("paper_always_enter", "DOGE/USDT", {"atr": 5.0})]
    pt = PaperTrader(s, _FakeSource([
        _frame([100] * 20),                 # tick 1 -> open at ~100
        _frame([100] * 21, last_low=90.0),  # tick 2 -> low 90 < stop ~95 -> stop out
    ]), db, combos)

    r1 = pt.tick(now_ms=2_000_000_000_000)
    assert r1["open_positions"] == 1
    r2 = pt.tick(now_ms=2_000_000_000_000)
    assert r2["open_positions"] == 0
    trades = db.recent_trades()
    assert len(trades) == 1 and trades[0]["reason"] == "stop"
    db.close()


def test_breaker_is_safe_hold_not_exit(tmp_path):
    s = _settings()
    s.raw["risk"]["daily_loss_limit"] = 0.001  # trivially trip after any loss
    db = Database(str(tmp_path / "b.db"))
    combos = [Combo("paper_always_enter", "PEPE/USDT", {"atr": 5.0})]
    pt = PaperTrader(s, _FakeSource([
        _frame([100] * 20),
        _frame([100] * 21, last_low=80.0),  # big loss -> breaker trips
        _frame([100] * 22),                 # still ticks; no new entry
    ]), db, combos)
    pt.tick(now_ms=2_000_000_000_000)
    pt.tick(now_ms=2_000_000_000_000)
    r3 = pt.tick(now_ms=2_000_000_000_000)
    # The process kept ticking (status returned), breaker active, no new position.
    assert r3["status"] == "safe_hold"
    assert r3["breaker"] is True
    assert r3["open_positions"] == 0
    db.close()


def test_restart_recovers_cash_and_positions(tmp_path):
    s = _settings()
    path = str(tmp_path / "r.db")
    db = Database(path)
    combos = [Combo("paper_always_enter", "WIF/USDT", {"atr": 5.0})]
    pt = PaperTrader(s, _FakeSource([_frame([100] * 20)]), db, combos)
    pt.tick(now_ms=2_000_000_000_000)
    cash_before = pt.cash
    assert len(pt.positions) == 1
    db.close()

    # New process: fresh Database + trader, recover from disk.
    db2 = Database(path)
    pt2 = PaperTrader(s, _FakeSource([_frame([100] * 20)]), db2, combos)
    pt2.recover_state()
    assert abs(pt2.cash - cash_before) < 1e-6
    assert ("paper_always_enter", "WIF/USDT") in pt2.positions
    db2.close()

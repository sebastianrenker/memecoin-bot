from __future__ import annotations

import yaml

from core.advisor import advise
from data.memecoin_filters import FilterVerdict


def test_failed_rug_check_forces_avoid():
    v = FilterVerdict(passed=False, reasons=["HONEYPOT: token cannot be sold (fatal)"], checked=8)
    a = advise(works_now_score=95, rug_verdict=v, attention=99)
    assert a.action == "avoid"  # safety overrides hype and a high score


def test_strong_edge_and_clean_rug_can_paper_consider():
    v = FilterVerdict(passed=True, reasons=[], checked=10)
    a = advise(works_now_score=80, rug_verdict=v, attention=60, n_trades=60, ruin_prob=0.0)
    assert a.action == "paper_consider"
    assert a.confidence > 0.4
    assert "paper" in a.disclaimer.lower()


def test_low_trades_and_ruin_downgrade_to_watch():
    v = FilterVerdict(passed=True, reasons=[], checked=10)
    a = advise(works_now_score=80, rug_verdict=v, n_trades=5, ruin_prob=0.3)
    assert a.action == "watch"          # confidence dampers pull it back from consider
    assert a.confidence < 0.5


def test_weak_edge_is_avoid():
    a = advise(works_now_score=20, rug_verdict=FilterVerdict(True, [], 6))
    assert a.action == "avoid"


def test_dex_combos_builder_from_watchlist(tmp_path):
    from cli import cmd_dex_combos

    wl = {"tokens": [
        {"symbol": "GOOD", "chain": "solana", "tradeable": True,
         "features": {"pool_address": "POOL1"}, "risk": {"passed": True, "reasons": [], "checked": 9}},
        {"symbol": "BAD", "chain": "solana", "tradeable": False,
         "features": {"pool_address": "POOL2"}, "risk": {"passed": False, "reasons": ["x"], "checked": 9}},
        {"symbol": "NOPOOL", "chain": "solana", "tradeable": True,
         "features": {"pool_address": ""}, "risk": {"passed": True, "reasons": [], "checked": 9}},
    ]}
    wpath = tmp_path / "wl.yaml"
    wpath.write_text(yaml.safe_dump(wl), encoding="utf-8")
    outp = tmp_path / "combos.yaml"

    class Args:
        watchlist = str(wpath)
        out = str(outp)
        strategies = "donchian_breakout,supertrend"
        tradeable_only = True
    rc = cmd_dex_combos(Args())
    assert rc == 0
    got = yaml.safe_load(outp.read_text(encoding="utf-8"))
    syms = {c["symbol"] for c in got["combos"]}
    assert syms == {"solana:POOL1"}                 # BAD (untradeable) + NOPOOL excluded
    assert len(got["combos"]) == 2                  # 1 token x 2 strategies

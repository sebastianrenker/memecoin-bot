"""Non-negotiable safety guarantees."""
from __future__ import annotations

import copy

import pytest

from config.settings import Settings
from execution.live import LiveBroker, LiveTradingNotEnabled


def test_live_broker_is_locked():
    with pytest.raises(LiveTradingNotEnabled):
        LiveBroker()
    with pytest.raises(LiveTradingNotEnabled):
        LiveBroker.create_order(object(), symbol="X", side="buy", amount=1)


def test_default_config_is_paper_and_valid():
    s = Settings.load()
    assert s.mode == "paper"
    assert s.validate() == []


def _mutated(**overrides):
    s = Settings.load()
    s.raw = copy.deepcopy(s.raw)
    for dotted, val in overrides.items():
        node = s.raw
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = val
    return s


def test_validate_rejects_live_mode():
    s = _mutated(mode="live")
    assert any("live" in p.lower() for p in s.validate())


def test_validate_rejects_fake_data_and_loose_risk():
    assert any("require_real" in p for p in _mutated(**{"data.require_real": False}).validate())
    assert any("risk_per_trade" in p for p in _mutated(**{"engine.risk_per_trade": 0.5}).validate())
    assert any("cost_multiplier" in p for p in _mutated(**{"engine.cost_multiplier": 0.5}).validate())
    assert any("min_stop_frac" in p for p in _mutated(**{"engine.min_stop_frac": 0.0}).validate())


def test_cli_backtest_skips_when_data_unavailable_offline(tmp_path, capsys):
    # DEX source rejects a non 'network:pool' symbol BEFORE any network call,
    # so this exercises the 'skip, don't fake' path fully offline.
    import yaml
    from cli import main
    cfg = {
        "mode": "paper",
        "data": {"require_real": True, "source": "dex", "timeframe": "1h",
                 "lookback_days": 30, "cache_dir": str(tmp_path / "c"),
                 "universe": ["DOGE/USDT"]},
        "engine": {"initial_equity": 10000, "cost_multiplier": 2.0, "min_stop_frac": 0.005,
                   "risk_per_trade": 0.01},
        "risk": {"daily_loss_limit": 0.03, "max_drawdown_kill": 0.25},
    }
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    rc = main(["--config", str(p), "backtest", "--strategy", "supertrend", "--symbol", "DOGE/USDT"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "No evaluation" in out and "faked" in out  # honest: nothing fabricated

"""Offline data-layer tests (no network): cache round-trip, normalization,
memecoin filters, and the require_real 'skip, don't fake' contract."""
from __future__ import annotations

import pandas as pd
import pytest

from data.base import DataUnavailable, normalize_ohlcv
from data.cache import OHLCVCache
from data.memecoin_filters import (FilterConfig, TokenMetadata, apply_filters)


def test_normalize_sorts_and_dedups():
    rows = [
        [3000, 1, 2, 0.5, 1.5, 10],
        [1000, 1, 2, 0.5, 1.5, 10],
        [1000, 1, 2, 0.5, 1.5, 10],  # dup timestamp
        [2000, 1, 2, 0.5, 1.5, 10],
    ]
    df = normalize_ohlcv(rows)
    assert list(df["timestamp"]) == [1000, 2000, 3000]
    assert df["close"].dtype == float


def test_cache_round_trip_and_ttl(tmp_path):
    cache = OHLCVCache(str(tmp_path), ttl_min=60)
    df = normalize_ohlcv([[1000, 1, 2, 0.5, 1.5, 10], [2000, 1, 2, 0.5, 1.5, 10]])
    cache.put("ccxt", "PEPE/USDT", "1h", df)
    got = cache.get("ccxt", "PEPE/USDT", "1h")
    assert got is not None and len(got) == 2
    # Expired TTL -> miss.
    expired = OHLCVCache(str(tmp_path), ttl_min=0)
    assert expired.get("ccxt", "PEPE/USDT", "1h") is None


def test_memecoin_filters_reject_thin_and_fresh():
    cfg = FilterConfig(min_liquidity_usd=50_000, min_age_days=30,
                       min_volume_usd=100_000, max_top10_holder_pct=0.6)
    bad = TokenMetadata("X", liquidity_usd=1_000, age_days=2, volume_24h_usd=500,
                        top10_holder_pct=0.9)
    v = apply_filters(bad, cfg)
    assert not v.passed and len(v.reasons) == 4

    good = TokenMetadata("Y", liquidity_usd=250_000, age_days=120,
                         volume_24h_usd=1_000_000, top10_holder_pct=0.2)
    assert apply_filters(good, cfg).passed


def test_unknown_fields_do_not_falsely_reject():
    # Missing metadata must not fabricate a pass/fail on that dimension.
    cfg = FilterConfig()
    meta = TokenMetadata("Z")  # all None
    assert apply_filters(meta, cfg).passed  # nothing known to reject on


def test_require_real_contract_raises_not_fakes():
    # A source that cannot fetch must raise DataUnavailable (caller skips it),
    # never return synthetic candles.
    from data.dex_source import DexSource
    ds = DexSource()
    with pytest.raises(DataUnavailable):
        ds.fetch_ohlcv("not-a-valid-symbol", "1h", 30)

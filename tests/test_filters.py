"""Upgraded rug-filter heuristics (pure, offline)."""
from __future__ import annotations

from data.memecoin_filters import (FilterConfig, TokenMetadata, apply_filters,
                                    merge_metadata)


def test_honeypot_and_authorities_are_hard_rejects():
    cfg = FilterConfig()
    hp = TokenMetadata("X", honeypot=True)
    v = apply_filters(hp, cfg)
    assert not v.passed and any("HONEYPOT" in r for r in v.reasons)

    live_mint = TokenMetadata("Y", mint_authority_active=True, freeze_authority_active=True,
                              lp_locked_or_burned=False)
    v2 = apply_filters(live_mint, cfg)
    assert not v2.passed
    joined = " ".join(v2.reasons)
    assert "mint authority" in joined and "freeze authority" in joined and "LP not locked" in joined


def test_concentration_and_rugcheck_score():
    cfg = FilterConfig()
    meta = TokenMetadata("Z", top_holder_pct=0.4, top10_holder_pct=0.8, insiders_pct=0.5,
                         rugcheck_score=90.0)
    v = apply_filters(meta, cfg)
    assert not v.passed and len(v.reasons) == 4


def test_clean_token_passes_and_counts_checks():
    cfg = FilterConfig()
    good = TokenMetadata(
        "OK", liquidity_usd=120_000, age_days=45, volume_24h_usd=500_000, holders=2000,
        unique_buyers_24h=800, top_holder_pct=0.05, top10_holder_pct=0.25, insiders_pct=0.05,
        mint_authority_active=False, freeze_authority_active=False, lp_locked_or_burned=True,
        honeypot=False, rugcheck_score=10.0)
    v = apply_filters(good, cfg)
    assert v.passed and v.checked >= 12


def test_unknown_fields_never_fabricate_a_verdict():
    v = apply_filters(TokenMetadata("Q"), FilterConfig())
    assert v.passed and v.checked == 0  # nothing known -> nothing rejected, nothing invented


def test_merge_metadata_first_non_none_wins():
    a = TokenMetadata("S", mint="m", holders=None, honeypot=True, risk_flags=["x"], source="goplus")
    b = TokenMetadata("S", mint="m", holders=1234, rugcheck_score=12.0, risk_flags=["y"], source="rugcheck")
    m = merge_metadata(a, b)
    assert m.holders == 1234 and m.honeypot is True and m.rugcheck_score == 12.0
    assert set(m.risk_flags) == {"x", "y"} and "rugcheck" in m.source and "goplus" in m.source

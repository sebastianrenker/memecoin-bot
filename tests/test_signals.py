"""Attention-signal scoring + watchlist (pure, offline).

These assert the honesty boundary too: attention ranks CURRENT activity, and the
rug filter still gates 'tradeable' independently of attention.
"""
from __future__ import annotations

from data.memecoin_filters import FilterConfig, TokenMetadata
from data.signals import (TokenFeatures, attention_score, build_signal,
                          build_watchlist, token_links)


def _hot():
    return TokenFeatures("HOT", "mintHOT", liquidity_usd=300_000, volume_24h_usd=4_000_000,
                         volume_5m_usd=40_000, buys_5m=300, sells_5m=100, boosts=20,
                         has_socials=True, age_hours=200)


def _quiet():
    return TokenFeatures("QUIET", "mintQUIET", liquidity_usd=5_000, volume_24h_usd=2_000,
                         volume_5m_usd=10, buys_5m=1, sells_5m=1, boosts=0,
                         has_socials=False, age_hours=1)


def test_attention_higher_for_active_token():
    assert attention_score(_hot()) > attention_score(_quiet())
    assert 0.0 <= attention_score(_quiet()) <= 100.0


def test_attention_is_bounded():
    huge = TokenFeatures("X", "m", liquidity_usd=1e12, volume_24h_usd=1e12,
                         volume_5m_usd=1e12, buys_5m=10**9, sells_5m=0, boosts=10**6,
                         has_socials=True)
    assert 0.0 <= attention_score(huge) <= 100.0


def test_high_attention_can_still_be_untradeable():
    # A hot token that is a honeypot must NOT be marked tradeable, regardless of buzz.
    f = _hot()
    meta = TokenMetadata(f.symbol, mint=f.mint, honeypot=True,
                         mint_authority_active=True, lp_locked_or_burned=False)
    s = build_signal(f, meta, FilterConfig())
    assert s.attention > 40
    assert s.tradeable is False
    assert any("HONEYPOT" in r for r in s.risk.reasons)


def test_watchlist_sorted_and_tradeable_filter():
    f_ok = _hot()
    meta_ok = TokenMetadata(f_ok.symbol, mint=f_ok.mint, holders=3000, unique_buyers_24h=900,
                            top_holder_pct=0.05, top10_holder_pct=0.25, insiders_pct=0.05,
                            mint_authority_active=False, freeze_authority_active=False,
                            lp_locked_or_burned=True, honeypot=False, rugcheck_score=8.0)
    f_bad = _quiet()
    meta_bad = TokenMetadata(f_bad.symbol, mint=f_bad.mint, honeypot=True)
    metas = {f_ok.mint: meta_ok, f_bad.mint: meta_bad}

    wl = build_watchlist([f_bad, f_ok], metas, FilterConfig())
    assert [s.symbol for s in wl] == ["HOT", "QUIET"]      # sorted by attention desc
    tradeable = build_watchlist([f_bad, f_ok], metas, FilterConfig(), tradeable_only=True)
    assert [s.symbol for s in tradeable] == ["HOT"]        # honeypot filtered out


def test_links_point_to_observation_venues():
    lk = token_links("MINT123", "solana")
    assert "rugcheck.xyz/tokens/MINT123" in lk["rugcheck"]
    assert "axiom.trade/t/MINT123" in lk["axiom"]
    assert "gmgn.ai/sol/token/MINT123" in lk["gmgn"]

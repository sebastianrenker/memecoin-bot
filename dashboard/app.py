"""Streamlit dashboard for the memecoin paper trader (read-only capable).

Run locally:   streamlit run dashboard/app.py
Cloud (public, read-only):  set CLOUD_READONLY=1 and TRADING_DB=cloud/paper.db

Everything shown is SIMULATED. Live trading is locked. Memecoins are extremely
risky and mostly go to zero — nothing here is a prediction or advice. The
"Signals" tab ranks current ATTENTION, never a forecast.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from persistence.db import Database  # noqa: E402

READONLY = os.environ.get("CLOUD_READONLY", "0") == "1"
DB_PATH = os.environ.get("TRADING_DB", os.path.join("cloud", "paper.db"))
WATCHLIST_PATH = os.environ.get("WATCHLIST", "watchlist.yaml")

_CSS = """
<style>
:root { --card:#12151c; --line:#262b36; --muted:#8b93a7; }
.block-container { padding-top: 1.2rem; max-width: 1300px; }
div[data-testid="stMetric"] {
  background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 14px 16px;
}
div[data-testid="stMetricLabel"] { color: var(--muted); }
.badge { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.8rem;
  font-weight:600; }
.badge.green { background:#123d24; color:#5ee08a; }
.badge.red   { background:#3d1414; color:#ff8a8a; }
.badge.amber { background:#3d3212; color:#f2c14e; }
.small { color: var(--muted); font-size:.85rem; }
a { text-decoration: none; }
</style>
"""


def _db() -> Database:
    return Database(DB_PATH)


def _banners() -> None:
    st.warning("**PAPER TRADING — SIMULATED MONEY ONLY.** Live trading is locked "
               "(`LiveTradingNotEnabled`). No real orders are ever placed.")
    st.error("**MEMECOIN RISK:** most memecoins go to zero; rugpulls are common, liquidity "
             "is thin, slippage is high. A positive short-term result is usually noise. "
             "Not investment advice, not a prediction.")


def _pill(text: str, kind: str) -> str:
    return f'<span class="badge {kind}">{text}</span>'


# --------------------------------------------------------------------------
def tab_live(db_path: str, auto: bool = False, secs: int = 15) -> None:
    # Only the Live tab auto-refreshes, and it reruns just this fragment in
    # place — so switching to other tabs is no longer interrupted by a full
    # page reload. The fragment opens its OWN db connection each run, because it
    # reruns after main() has already closed the shared one.
    interval = f"{secs}s" if auto else None
    try:
        runner = st.fragment(run_every=interval)
    except Exception:
        runner = (lambda f: f)  # very old Streamlit: just render once

    @runner
    def _render():
        db = Database(db_path)
        try:
            _render_live(db)
        finally:
            db.close()
    _render()
    # Heavy per-coin charts render outside the auto-refresh fragment (network).
    _render_all_charts(db_path)


def _render_live(db: Database) -> None:
    row = db.conn.execute("SELECT * FROM heartbeat WHERE id=1").fetchone()
    hb = dict(row) if row else {}
    eq = db.last_equity()
    positions = db.load_positions()
    trades = db.recent_trades(500)

    status = hb.get("status", "unknown")
    kind = "green" if status == "running" else ("amber" if status == "safe_hold" else "red")
    st.markdown(f"### Live Paper-Trader &nbsp; {_pill(status, kind)}", unsafe_allow_html=True)

    # --- "Macht er Geld?" — the profit verdict (paper / theoretical) -------
    curve = db.equity_curve(20000)
    start_eq = curve[0][1] if curve else 10000.0
    cur_eq = (eq if eq is not None else (curve[-1][1] if curve else start_eq))
    pnl_abs = cur_eq - start_eq
    pnl_pct = (pnl_abs / start_eq * 100.0) if start_eq else 0.0
    realized = sum(t["pnl"] for t in trades)
    gp = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gl = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    pf = (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0)
    wins = [t for t in trades if t["pnl"] > 0]
    wr = (len(wins) / len(trades) * 100.0) if trades else 0.0
    unrealized = pnl_abs - realized

    up = pnl_abs >= 0
    color = "#123d24" if up else "#3d1414"
    fg = "#5ee08a" if up else "#ff8a8a"
    verdict = "✅ Macht Geld (Paper)" if pnl_abs > 0 else (
        "➖ Bei ±0 (Paper)" if abs(pnl_abs) < 1e-9 else "🔻 Verliert Geld (Paper)")
    st.markdown(
        f'<div style="background:{color};border:1px solid {fg}33;border-radius:14px;'
        f'padding:14px 18px;margin:6px 0 12px">'
        f'<div style="color:{fg};font-size:1.5rem;font-weight:800">{verdict} &nbsp; '
        f'{pnl_pct:+.2f}% &nbsp;<span style="font-size:1rem">({pnl_abs:+,.2f} sim)</span></div>'
        f'<div style="color:#c9d2e0;font-size:.82rem;margin-top:4px">'
        f'Start {start_eq:,.0f} → jetzt {cur_eq:,.2f} · realisiert {realized:+,.2f} · '
        f'offen (unrealisiert) {unrealized:+,.2f} · theoretisch/simuliert, kein echtes Geld</div>'
        f'</div>', unsafe_allow_html=True)

    # KPIs
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Equity (sim)", f"{cur_eq:,.2f}", f"{pnl_pct:+.2f}%")
    m2.metric("P&L (sim)", f"{pnl_abs:+,.2f}")
    m3.metric("Win rate", f"{wr:.0f}%", f"{len(wins)}/{len(trades)}")
    m4.metric("Profit factor", "∞" if pf == float("inf") else f"{pf:.2f}")
    m5.metric("Open positions", len(positions))
    age = (time.time() * 1000 - hb["ts"]) / 1000 if hb.get("ts") else None
    m6.metric("Heartbeat age", f"{age:.0f}s" if age is not None else "-")

    if not READONLY:
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("⏸ Stop (safe)"):
            db.set_control("command", "stop"); st.success("Stop requested.")
        if c2.button("▶ Run"):
            db.set_control("command", "run"); st.success("Run requested.")
        if c3.button("Reset daily breaker"):
            db.set_control("reset_breaker", "1"); st.success("Breaker reset requested.")
        if c4.button("Clear kill switch"):
            db.set_control("kill_tripped", "0"); st.success("Kill switch cleared.")
    else:
        st.caption("Read-only cloud view — control buttons are hidden.")

    st.markdown("#### Equity curve (simulated)")
    curve = db.equity_curve(5000)
    if curve:
        ec = pd.DataFrame(curve, columns=["ts", "equity"])
        ec["time"] = pd.to_datetime(ec["ts"], unit="ms")
        try:
            import altair as alt
            area = alt.Chart(ec).mark_area(opacity=0.25, line=True).encode(
                x=alt.X("time:T", title=None), y=alt.Y("equity:Q", scale=alt.Scale(zero=False)))
            st.altair_chart(area.interactive(), use_container_width=True)
        except Exception:
            st.line_chart(ec.set_index("time")["equity"])
    else:
        st.caption("No equity points yet. Run `python cli.py ci-tick`.")

    cA, cB = st.columns(2)
    with cA:
        st.markdown("#### Open positions")
        st.dataframe(pd.DataFrame(positions) if positions
                     else pd.DataFrame(columns=["strategy", "symbol"]), use_container_width=True)
    with cB:
        st.markdown("#### Recent trades (simulated)")
        st.dataframe(pd.DataFrame(trades[:20]) if trades
                     else pd.DataFrame(columns=["strategy", "symbol", "pnl"]),
                     use_container_width=True)


@st.cache_data(ttl=120, show_spinner=False)
def _load_candles(symbol: str, timeframe: str, days: int):
    """Fetch real candles for a symbol (ccxt for CEX, GeckoTerminal for on-chain).
    Cached briefly so the charts don't hammer the APIs."""
    from core.utils import closed_bars
    if ":" in symbol:
        from data.dex_source import DexSource
        src = DexSource()
    else:
        from data.ccxt_source import CcxtSource
        src = CcxtSource("binance")
    raw = src.fetch_ohlcv(symbol, timeframe, days)
    df = closed_bars(raw, timeframe).tail(400).copy()
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def _twitter_link(symbol: str) -> str:
    import urllib.parse as u
    base = symbol.split("/")[0]
    if ":" not in symbol and base.isalnum():
        return "https://x.com/search?q=" + u.quote("$" + base) + "&f=live"
    return "https://x.com/search?q=" + u.quote(symbol) + "&f=live"


def _coin_chart(symbol: str, timeframe: str, days: int, trades, position) -> None:
    import altair as alt
    try:
        df = _load_candles(symbol, timeframe, days)
        if df is None or len(df) < 3:
            st.caption(f"{symbol}: no candles.")
            return
    except Exception as e:
        st.caption(f"{symbol}: could not load candles ({e}).")
        return

    base = alt.Chart(df).encode(x=alt.X("time:T", title=None))
    wick = base.mark_rule().encode(y=alt.Y("low:Q", title="Kurs", scale=alt.Scale(zero=False)),
                                   y2="high:Q",
                                   color=alt.condition("datum.close >= datum.open",
                                                       alt.value("#2ca02c"), alt.value("#d62728")))
    body = base.mark_bar(size=3).encode(
        y="open:Q", y2="close:Q",
        color=alt.condition("datum.close >= datum.open", alt.value("#2ca02c"), alt.value("#d62728")))
    layers = [wick, body]

    # Entry (buy) and exit (sell) markers from this symbol's trades.
    st_trades = [t for t in trades if t["symbol"] == symbol]
    entries = [{"time": pd.to_datetime(t["ts_open"], unit="ms"), "price": t["entry"],
                "strat": t["strategy"]} for t in st_trades if t.get("ts_open")]
    exits = [{"time": pd.to_datetime(t["ts_close"], unit="ms"), "price": t["exit"],
              "pnl": t["pnl"], "reason": t["reason"]} for t in st_trades if t.get("ts_close")]
    if entries:
        em = alt.Chart(pd.DataFrame(entries)).mark_point(
            shape="triangle-up", size=140, filled=True, color="#33d17a").encode(
            x="time:T", y="price:Q", tooltip=["strat", "price"])
        layers.append(em)
    if exits:
        xm = alt.Chart(pd.DataFrame(exits)).mark_point(
            shape="triangle-down", size=140, filled=True).encode(
            x="time:T", y="price:Q",
            color=alt.condition("datum.pnl >= 0", alt.value("#2ca02c"), alt.value("#d62728")),
            tooltip=["price", "pnl", "reason"])
        layers.append(xm)

    # Open-position lines: entry (blue), stop (red dashed), take-profit (green dashed).
    if position:
        def _hline(val, color, dash):
            return alt.Chart(pd.DataFrame({"y": [val]})).mark_rule(
                color=color, strokeDash=dash, size=1.5).encode(y="y:Q")
        layers.append(_hline(position["entry"], "#4c8dff", [1, 0]))
        layers.append(_hline(position["stop"], "#ff6b6b", [5, 4]))
        if position.get("tp") is not None:
            layers.append(_hline(position["tp"], "#33d17a", [5, 4]))

    st.altair_chart(alt.layer(*layers).resolve_scale(y="shared").interactive(),
                    use_container_width=True)


def _render_all_charts(db_path: str) -> None:
    st.markdown("### Charts — Ein-/Ausstieg, Stop-Loss & Take-Profit pro Coin")
    st.caption("🟢 Kauf-Einstieg · 🔻 Verkauf · blaue Linie = Entry · rote gestrichelte = Stop-Loss · "
               "grüne gestrichelte = Take-Profit. Kerzen = echter Kurs.")
    try:
        import altair  # noqa: F401
    except Exception as e:
        st.caption(f"Charts brauchen altair: {e}")
        return
    db = Database(db_path)
    try:
        positions = db.load_positions()
        trades = db.recent_trades(1000)
    finally:
        db.close()

    pos_by_sym = {p["symbol"]: p for p in positions}
    traded = sorted({t["symbol"] for t in trades})
    all_syms = sorted(set(pos_by_sym) | set(traded))
    if not all_syms:
        st.caption("Noch keine Trades/Positionen — sobald der Bot handelt, erscheinen hier die Charts.")
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    tf = c1.selectbox("Timeframe", ["5m", "15m", "1h", "1m"], index=0)
    days = c2.slider("Tage", 1, 30, 3)
    default = [s for s in all_syms if s in pos_by_sym] or all_syms[:4]
    chosen = c3.multiselect("Coins", all_syms, default=default)
    if c1.button("🔄 Charts aktualisieren"):
        _load_candles.clear()

    for sym in chosen:
        pos = pos_by_sym.get(sym)
        held = " · 🟢 offen" if pos else ""
        st.markdown(f"#### {sym}{held}")
        # Twitter + wallet/verify links per coin.
        base = sym.split('/')[0]
        links = [f"[𝕏 Twitter (live)]({_twitter_link(sym)})",
                 f"[GMGN smart-money](https://gmgn.ai/?chain=sol&q={base})",
                 f"[DexScreener](https://dexscreener.com/search?q={base})"]
        if ":" in sym:
            mint = sym.split(":", 1)[1]
            links = [f"[𝕏 Twitter (live)]({_twitter_link(sym)})",
                     f"[RugCheck](https://rugcheck.xyz/tokens/{mint})",
                     f"[GMGN Radar](https://gmgn.ai/sol/token/{mint})",
                     f"[Axiom](https://axiom.trade/t/{mint})"]
        st.markdown(" · ".join(links))
        if pos:
            st.caption(f"Entry {pos['entry']:.6g} · Stop {pos['stop']:.6g}"
                       + (f" · TP {pos['tp']:.6g}" if pos.get("tp") is not None else "")
                       + f" · Menge {pos['qty']:.4g}")
        _coin_chart(sym, tf, days, trades, pos)


_DISCOVER_CSS = """
<style>
.ax-legend{color:#8b93a7;font-size:.75rem;margin:.2rem 0 .6rem}
.ax-head{display:grid;grid-template-columns:1.7fr .95fr .8fr 1fr 1fr .95fr .7fr 1.1fr 1.5fr;
  gap:8px;color:#7f889c;font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;
  padding:4px 12px}
.ax-row{display:grid;grid-template-columns:1.7fr .95fr .8fr 1fr 1fr .95fr .7fr 1.1fr 1.5fr;
  gap:8px;align-items:center;background:#121722;border:1px solid #1e2430;border-radius:10px;
  padding:9px 12px;margin-bottom:6px}
.ax-row:hover{border-color:#2b64ff;background:#141b28}
.ax-sym{font-weight:700;font-size:.95rem}
.ax-mint{color:#6b7488;font-size:.66rem}
.chip{padding:1px 7px;border-radius:6px;font-size:.66rem;font-weight:700;margin-left:6px}
.chip.solana{background:#2e2559;color:#c4b5fd}.chip.bsc{background:#4d3f12;color:#f2c14e}
.chip.ethereum{background:#22314d;color:#8ab4ff}.chip.base{background:#123a52;color:#7fd7ff}
.num{font-variant-numeric:tabular-nums}
.pos{color:#33d17a}.neg{color:#ff6b6b}.mut{color:#8b93a7}
.pill{padding:2px 8px;border-radius:999px;font-size:.7rem;font-weight:700;text-align:center}
.pill.ok{background:#123d24;color:#5ee08a}.pill.no{background:#3d1414;color:#ff8a8a}
.abar{height:7px;background:#1e2430;border-radius:5px;overflow:hidden;min-width:60px}
.abar>i{display:block;height:100%;background:linear-gradient(90deg,#2b64ff,#14e0a0)}
.acts a{padding:2px 8px;border-radius:7px;background:#1b2130;border:1px solid #2a3342;
  color:#cbd3e1;font-size:.7rem;text-decoration:none;margin-right:4px;white-space:nowrap}
.acts a.x{color:#8ab4ff;border-color:#2a3a5a}.acts a.ax{color:#14e0a0;border-color:#1c4a3a}
.acts a.rc{color:#f2b3b3;border-color:#4a2a2a}
/* Axiom-style column board */
.axcolhead{display:flex;justify-content:space-between;align-items:center;
  font-weight:700;font-size:.85rem;color:#e6e9ef;padding:6px 8px;border-bottom:1px solid #1e2430;
  position:sticky;top:0;background:#0a0e17;z-index:2}
.axcolhead .cnt{color:#7f889c;font-size:.72rem;font-weight:600}
.axcol{max-height:74vh;overflow-y:auto;padding-right:4px}
.axcol::-webkit-scrollbar{width:8px}.axcol::-webkit-scrollbar-thumb{background:#232a38;border-radius:8px}
.axc{background:#121722;border:1px solid #1e2430;border-radius:10px;padding:8px 10px;margin:6px 0}
.axc:hover{border-color:#2b64ff;background:#141b28}
.axc.no{border-left:3px solid #7a2a2a}.axc.ok{border-left:3px solid #1c5a3a}
.axc-h{display:flex;align-items:center;gap:6px}
.axc-h .age{margin-left:auto;color:#7f889c;font-size:.68rem}
.axc-p{display:flex;gap:10px;align-items:baseline;margin:3px 0}
.axc-p .price{font-weight:700}
.axc-s{color:#9aa3b5;font-size:.72rem;font-variant-numeric:tabular-nums}
.axc-f{display:flex;align-items:center;gap:6px;margin-top:6px}
</style>
"""


def _fmt_usd(x) -> str:
    try:
        x = float(x or 0)
    except Exception:
        return "-"
    if x >= 1e9:
        return f"${x/1e9:.2f}B"
    if x >= 1e6:
        return f"${x/1e6:.2f}M"
    if x >= 1e3:
        return f"${x/1e3:.1f}k"
    return f"${x:,.0f}"


def _fmt_price(x) -> str:
    try:
        x = float(x or 0)
    except Exception:
        return "-"
    if x == 0:
        return "-"
    if x >= 1:
        return f"${x:,.4f}"
    return f"${x:.8f}".rstrip("0").rstrip(".")


def _esc(s) -> str:
    import html as _h
    return _h.escape(str(s if s is not None else ""))


def tab_discover() -> None:
    st.markdown("### Discover — live coins, classified")
    st.markdown('<div class="ax-legend">Axiom-style board of the currently-active coins: '
                'on-chain data, risk classification, an attention rank (activity NOW, not a '
                'forecast), and a one-click link to the LIVE X/Twitter feed per coin. No free '
                'reliable auto-sentiment exists, so you get the real feed. Paper only.</div>',
                unsafe_allow_html=True)
    if not os.path.exists(WATCHLIST_PATH):
        st.caption(f"No `{WATCHLIST_PATH}` yet. Run `python cli.py scan --chains sol,bnb,eth`.")
        return
    try:
        import yaml
        data = yaml.safe_load(open(WATCHLIST_PATH, encoding="utf-8")) or {}
    except Exception as e:
        st.caption(f"Could not read watchlist: {e}")
        return
    tokens = data.get("tokens", [])
    if not tokens:
        st.caption("Watchlist is empty.")
        return

    # Controls
    chains = sorted({t.get("chain", "solana") for t in tokens})
    c1, c2, c3 = st.columns([2, 1, 1])
    sel_chains = c1.multiselect("Chains", chains, default=chains)
    only_ok = c2.checkbox("Tradeable only", value=False)
    sort_by = c3.selectbox("Sort", ["attention", "market cap", "24h %", "volume"])
    view = [t for t in tokens if t.get("chain", "solana") in sel_chains
            and (t.get("tradeable") if only_ok else True)]
    keyf = {"attention": lambda t: t.get("attention", 0),
            "market cap": lambda t: (t.get("features", {}).get("market_cap")
                                     or t.get("features", {}).get("fdv") or 0),
            "24h %": lambda t: t.get("features", {}).get("price_change_24h", 0),
            "volume": lambda t: t.get("features", {}).get("volume_24h_usd", 0)}[sort_by]
    view.sort(key=keyf, reverse=True)

    st.markdown(_DISCOVER_CSS, unsafe_allow_html=True)

    def _card(t) -> str:
        f, lk = t.get("features", {}), t.get("links", {})
        chain = t.get("chain", "solana")
        ch24 = f.get("price_change_24h", 0) or 0
        chcls = "pos" if ch24 >= 0 else "neg"
        ok = bool(t.get("tradeable"))
        att = float(t.get("attention", 0) or 0)
        age_h = f.get("age_hours", 0) or 0
        age = f"{age_h/24:.1f}d" if age_h >= 24 else f"{age_h:.0f}h"
        acts = []
        if lk.get("x_search"):
            acts.append(f'<a class="x" target="_blank" href="{_esc(lk["x_search"])}">X</a>')
        if lk.get("axiom"):
            acts.append(f'<a class="ax" target="_blank" href="{_esc(lk["axiom"])}">Axiom</a>')
        if lk.get("rugcheck"):
            acts.append(f'<a class="rc" target="_blank" href="{_esc(lk["rugcheck"])}">Rug</a>')
        if lk.get("gmgn"):
            acts.append(f'<a target="_blank" href="{_esc(lk["gmgn"])}">GMGN</a>')
        if lk.get("dexscreener"):
            acts.append(f'<a target="_blank" href="{_esc(lk["dexscreener"])}">Dex</a>')
        return (
            f'<div class="axc {"ok" if ok else "no"}">'
            f'<div class="axc-h"><b>{_esc(t.get("symbol"))}</b>'
            f'<span class="chip {chain}">{_esc(chain)}</span>'
            f'<span class="age">{age}</span></div>'
            f'<div class="axc-p"><span class="price num">{_fmt_price(f.get("price_usd"))}</span>'
            f'<span class="num {chcls}">{ch24:+.1f}%</span>'
            f'<span class="mut" style="margin-left:auto;font-size:.68rem">att {att:.0f}</span></div>'
            f'<div class="axc-s">MC {_fmt_usd(f.get("market_cap") or f.get("fdv"))} · '
            f'Liq {_fmt_usd(f.get("liquidity_usd"))} · Vol {_fmt_usd(f.get("volume_24h_usd"))}</div>'
            f'<div class="axc-f"><span class="pill {"ok" if ok else "no"}">'
            f'{"tradeable" if ok else "avoid"}</span><span class="acts">{"".join(acts)}</span></div>'
            f'</div>')

    feed_titles = [("new", "🆕 New"), ("trending", "🔥 Trending"),
                   ("top", "📊 Top Volume"), ("boosted", "🚀 Boosted")]
    present = [(fid, title) for fid, title in feed_titles
               if any(t.get("features", {}).get("feed") == fid for t in view)]
    if not present:
        present = [("", "All coins")]

    cols = st.columns(len(present))
    for (fid, title), col in zip(present, cols):
        items = [t for t in view if (fid == "" or t.get("features", {}).get("feed") == fid)]
        cards = "".join(_card(t) for t in items) or '<div class="mut" style="padding:8px">none</div>'
        col.markdown(f'<div class="axcolhead">{title}<span class="cnt">{len(items)}</span></div>'
                     f'<div class="axcol">{cards}</div>', unsafe_allow_html=True)

    n_ok = sum(1 for t in tokens if t.get("tradeable"))
    st.caption(f"{len(view)} coins shown · {len(tokens)} scanned · {n_ok} passed the rug filters. "
               "Green cards passed, red did not. Most coins fail — the honest reality, not a bug. "
               "Attention = activity now, not a forecast.")

    with st.expander("Per-coin detail (all data + flags + links)"):
        labels = [f"{t.get('symbol')} · {t.get('chain')} · {t.get('features',{}).get('feed','')}"
                  for t in view]
        if labels:
            pick = st.selectbox("Coin", labels)
            tok = view[labels.index(pick)]
            f, lk = tok.get("features", {}), tok.get("links", {})
            st.write("**Risk flags:** " +
                     ("; ".join(tok.get("risk", {}).get("reasons", [])) or "none known"))
            st.json({k: f.get(k) for k in
                     ["price_usd", "liquidity_usd", "volume_24h_usd", "market_cap", "fdv",
                      "price_change_1h", "price_change_6h", "price_change_24h", "age_hours",
                      "buys_5m", "sells_5m", "boosts", "dex", "feed", "pool_address"] if k in f})
            st.markdown("**Links:** " + " · ".join(
                f"[{name}]({url})" for name, url in lk.items() if url))


def tab_observe() -> None:
    st.markdown("### Observe on Axiom / MockApe")
    st.info("This bot is **paper-only** and never places real orders, so there is nothing "
            "to route to a live venue. Here is the honest way to 'follow what the bot does' "
            "and to practice as realistically as possible:")
    st.markdown(
        "- **Watch the same tokens on Axiom** — open any token from the *Signals* tab via its "
        "`observe` link (`axiom.trade/t/<mint>`). Axiom shows live price, wallet activity and "
        "X/Twitter sentiment for that token. You are *observing*, not letting the bot trade.\n"
        "- **MockApe** (browser extension) adds **paper trading directly inside Axiom, Padre and "
        "GMGN** with virtual money and real-time data — the closest-to-real practice without "
        "risking funds. Use it to manually mirror the bot's paper decisions on Axiom's UI.\n"
        "- **Track smart-money wallets** on **GMGN** (free leaderboards / Radar: earliest, "
        "heaviest and most-profitable buyers) or **Cielo/Nansen** (paid) — use the `GMGN` link "
        "per token.\n"
        "- **Verify safety** on **RugCheck** (mint/freeze authority, LP lock, holder "
        "concentration, insiders) via the `RugCheck` link before you ever risk real money.")
    st.warning("Going from paper to real money is a decision only you can make and own. The "
               "research is blunt: most memecoin traders lose, and 'attention' is not an edge.")


def tab_ranking(db: Database) -> None:
    st.markdown("### Strategy ranking (latest evaluations)")
    evals = db.latest_evaluations(500)
    if not evals:
        st.caption("No evaluations yet. Run `python cli.py rank --db`.")
        return
    df = pd.DataFrame(evals).sort_values("id").drop_duplicates(["strategy", "symbol"], keep="last")
    df = df.sort_values("score", ascending=False)
    st.dataframe(df[["light", "score", "strategy", "symbol", "expectancy_r",
                     "n_trades", "mean_efficiency", "ruin_prob"]], use_container_width=True)


def tab_detail(db: Database) -> None:
    st.markdown("### Detail (score decomposition)")
    evals = db.latest_evaluations(500)
    if not evals:
        st.caption("No evaluations yet.")
        return
    df = pd.DataFrame(evals).sort_values("id").drop_duplicates(["strategy", "symbol"], keep="last")
    label = st.selectbox("Combo", [f"{r.strategy}@{r.symbol}" for r in df.itertuples()])
    strat, sym = label.split("@")
    row = df[(df["strategy"] == strat) & (df["symbol"] == sym)].iloc[0]
    extra = json.loads(row["extra"]) if row["extra"] else {}
    st.metric("Score", f"{row['score']:.1f}", row["light"])
    st.write("**Sub-scores**", extra.get("subscores", {}))
    st.write("**Warnings**")
    for w in extra.get("warnings", []):
        st.write(f"- {w}")
    st.write("**Params (validated)**", extra.get("params", {}))


def tab_heatmap(db: Database) -> None:
    st.markdown("### Heatmap (score by strategy × symbol)")
    evals = db.latest_evaluations(1000)
    if not evals:
        st.caption("No evaluations yet.")
        return
    df = pd.DataFrame(evals).sort_values("id").drop_duplicates(["strategy", "symbol"], keep="last")
    pivot = df.pivot_table(index="strategy", columns="symbol", values="score", aggfunc="last")

    def _color(v):
        if v != v:
            return ""
        v = max(0.0, min(100.0, float(v)))
        if v < 50:
            r, g = 220, int(60 + (v / 50.0) * 160)
        else:
            r, g = int(220 - ((v - 50) / 50.0) * 180), 200
        return f"background-color: rgb({r},{g},60); color:#111"

    st.dataframe(pivot.style.applymap(_color).format("{:.0f}"), use_container_width=True)


def tab_audit(db: Database) -> None:
    st.markdown("### Audit log")
    st.dataframe(pd.DataFrame(db.recent_audit(300)), use_container_width=True)


def _pick_db_path() -> str:
    """Sidebar switch between the CEX paper bot and the on-chain paper bot.

    Both trade SIMULATED money on REAL data (ccxt vs GeckoTerminal). The env
    default (TRADING_DB) is honoured as the initial selection.
    """
    candidates = {
        "Live paper (active demo, real 5m data)": os.path.join("cloud", "live.db"),
        "CEX paper (real ccxt data)": os.path.join("cloud", "paper.db"),
        "On-chain paper (real GeckoTerminal data)": os.path.join("cloud", "dex.db"),
    }
    # Include the env-configured DB if it's something else entirely.
    if DB_PATH not in candidates.values():
        candidates[f"Configured ({DB_PATH})"] = DB_PATH
    labels = list(candidates)
    default_idx = next((i for i, l in enumerate(labels) if candidates[l] == DB_PATH), 0)
    with st.sidebar:
        st.markdown("### Bot view")
        st.caption("All are paper (simulated money) on real market data.")
        choice = st.radio("Data source", labels, index=default_idx)
        path = candidates[choice]
        st.caption(f"DB: `{path}`" + ("" if os.path.exists(path) else "  · not created yet"))
        st.markdown("### Live view")
        auto = st.checkbox("Auto-refresh (Live tab only)", value=True)
        secs = st.slider("Every N seconds", 5, 60, 15, disabled=not auto)
        st.caption("Refreshes only the Live tab in place — other tabs stay put.")
    return path, auto, secs


def main() -> None:
    st.set_page_config(page_title="Memecoin Paper Trader", layout="wide", page_icon="🎲")
    st.markdown(_CSS, unsafe_allow_html=True)
    st.title("🎲 Memecoin Paper-Trading Analysis")
    _banners()
    db_path, auto, secs = _pick_db_path()
    if not os.path.exists(db_path):
        st.info(f"No database yet at `{db_path}`. Run the matching bot "
                "(`ci-tick` for CEX, `dex-bot`/config_dex for on-chain) first.")
    db = Database(db_path) if os.path.exists(db_path) else None

    tabs = st.tabs(["📈 Live", "🔎 Discover", "👁 Observe", "🏆 Ranking",
                    "🔬 Detail", "🗺 Heatmap", "📜 Audit"])
    with tabs[0]:
        tab_live(db_path, auto, secs) if db else st.caption("No data yet.")
    with tabs[1]:
        tab_discover()
    with tabs[2]:
        tab_observe()
    with tabs[3]:
        tab_ranking(db) if db else st.caption("No data yet.")
    with tabs[4]:
        tab_detail(db) if db else st.caption("No data yet.")
    with tabs[5]:
        tab_heatmap(db) if db else st.caption("No data yet.")
    with tabs[6]:
        tab_audit(db) if db else st.caption("No data yet.")
    if db:
        db.close()


if __name__ == "__main__":
    main()

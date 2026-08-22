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
DB_PATH = os.environ.get("TRADING_DB", os.path.join("cloud", "live.db"))
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
    st.warning("**PAPER-TRADING — NUR SIMULIERTES GELD.** Live-Handel ist gesperrt "
               "(`LiveTradingNotEnabled`). Es werden **nie** echte Orders platziert.")
    st.error("**MEMECOIN-RISIKO:** die meisten Memecoins gehen gegen null; Rugpulls sind "
             "häufig, Liquidität dünn, Slippage hoch. Ein kurzfristiges Plus ist meist "
             "Rauschen. Keine Anlageberatung, keine Prognose.")


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
    # Full trade evaluation (db-only) after the charts.
    _db = Database(db_path)
    try:
        _render_trade_analytics(_db.recent_trades(5000))
    finally:
        _db.close()


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
    _init = db.get_meta("initial_equity")
    start_eq = float(_init) if _init else (curve[0][1] if curve else 10000.0)
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

    # Live mark-to-market: override the stale last-tick equity with current prices
    # of the open positions, so the headline matches the per-coin live P&L. Uses the
    # multi-exchange fallback in _load_candles, so it also works on Streamlit Cloud.
    cash_meta = db.get_meta("cash")
    live = False
    if positions and cash_meta is not None:
        try:
            live_unreal = 0.0
            for p in positions:
                cdf = _load_candles(p["symbol"], "5m", 2)
                live_unreal += p["qty"] * (float(cdf["close"].iloc[-1]) - p["entry"])
            cur_eq = float(cash_meta) + live_unreal
            unrealized = live_unreal
            pnl_abs = cur_eq - start_eq
            pnl_pct = (pnl_abs / start_eq * 100.0) if start_eq else 0.0
            live = True
        except Exception:
            live = False

    up = pnl_abs >= 0
    color = "#123d24" if up else "#3d1414"
    fg = "#5ee08a" if up else "#ff8a8a"
    head = ("✅ Du bist im PLUS (Paper)" if pnl_abs > 0 else
            ("➖ Genau bei ±0 (Paper)" if abs(pnl_abs) < 1e-9 else "🔻 Du bist im MINUS (Paper)"))
    livetag = "  · Live-Kurs" if live else "  · Stand letzter Tick"
    st.markdown(
        f'<div style="background:{color};border:1px solid {fg}44;border-radius:16px;'
        f'padding:18px 22px;margin:6px 0 14px">'
        f'<div style="color:#c9d2e0;font-size:.9rem">Aus {start_eq:,.0f} € sind aktuell geworden{livetag}</div>'
        f'<div style="color:{fg};font-size:2.4rem;font-weight:800;line-height:1.1">{cur_eq:,.2f} €</div>'
        f'<div style="color:{fg};font-size:1.35rem;font-weight:800">{pnl_abs:+,.2f} €'
        f'&nbsp;<span style="font-size:1rem">({pnl_pct:+.2f} %)</span></div>'
        f'<div style="color:#e6e9ef;font-size:1.05rem;margin-top:8px;font-weight:700">{head}</div>'
        f'<div style="color:#c9d2e0;font-size:.82rem;margin-top:4px">'
        f'Fest verbucht (abgeschlossene Trades): <b>{realized:+,.2f} €</b> · '
        f'Noch offen (schwankt bis zum Verkauf): <b>{unrealized:+,.2f} €</b> · '
        f'virtuelle €, simuliert, kein echtes Geld</div>'
        f'</div>', unsafe_allow_html=True)

    # --- Kosten & Steuern (Schätzung) ------------------------------------
    total_fees = sum(t.get("fees", 0.0) for t in trades)
    tax_rate = st.session_state.get("tax_rate", 0.26)
    free_limit = st.session_state.get("tax_free", 1000)
    taxable = realized if realized > free_limit else 0.0
    tax = tax_rate * taxable
    net_after = realized - tax
    st.markdown("##### 💶 Kosten & Steuern (Schätzung — **keine Steuerberatung**)")
    k = st.columns(4)
    k[0].metric("Gebühren gezahlt", f"{total_fees:,.2f} €")
    k[1].metric("Realisiert (nach Gebühren)", f"{realized:+,.2f} €")
    k[2].metric(f"Steuer (~{tax_rate*100:.0f}%)", f"-{tax:,.2f} €")
    k[3].metric("Netto nach Steuer", f"{net_after:+,.2f} €")
    st.caption(f"Grobe Schätzung. Freigrenze {free_limit:,.0f} €/Jahr (bis dahin steuerfrei — "
               "typisch für private Veräußerungsgeschäfte in DE bei Haltedauer < 1 Jahr). Nur "
               "**realisierte** Gewinne werden besteuert, offene nicht. Gebühren sind bereits "
               "im P&L abgezogen. Das ist **keine Steuerberatung** — frag eine:n Steuerberater:in. "
               "Satz in der Sidebar einstellbar.")

    # KPIs
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Kapital (Paper)", f"{cur_eq:,.2f} €", f"{pnl_pct:+.2f}%")
    m2.metric("G/V (Paper)", f"{pnl_abs:+,.2f} €")
    m3.metric("Trefferquote", f"{wr:.0f}%", f"{len(wins)}/{len(trades)}")
    m4.metric("Profit-Faktor", "∞" if pf == float("inf") else f"{pf:.2f}")
    m5.metric("Offene Pos.", len(positions))
    age = (time.time() * 1000 - hb["ts"]) / 1000 if hb.get("ts") else None
    m6.metric("Letzter Tick", f"vor {age:.0f}s" if age is not None else "-")

    if not READONLY:
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("⏸ Stop (sicher)"):
            db.set_control("command", "stop"); st.success("Stop angefordert.")
        if c2.button("▶ Weiter"):
            db.set_control("command", "run"); st.success("Weiter angefordert.")
        if c3.button("Tages-Breaker zurücksetzen"):
            db.set_control("reset_breaker", "1"); st.success("Breaker-Reset angefordert.")
        if c4.button("Kill-Switch löschen"):
            db.set_control("kill_tripped", "0"); st.success("Kill-Switch gelöscht.")
    else:
        st.caption("Nur-Lese-Cloud-Ansicht — Steuerung ausgeblendet.")

    st.markdown("#### Kapitalkurve (Paper)")
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

    st.markdown("#### Offene Positionen")
    if positions:
        pv = pd.DataFrame(positions)[["strategy", "symbol", "side", "qty", "entry", "stop", "tp"]]
        st.dataframe(pv, use_container_width=True, hide_index=True)
    else:
        st.caption("Keine offenen Positionen.")


def _render_trade_analytics(trades) -> None:
    import numpy as np
    st.markdown("#### Trade-Auswertung (geschlossene Trades)")
    closed = [t for t in trades if t.get("ts_close")]
    if not closed:
        st.caption("Noch keine geschlossenen Trades — die Auswertung erscheint, sobald der Bot "
                   "die erste Position schließt (Stop, Take-Profit oder Signal).")
        return
    df = pd.DataFrame(closed)
    r = df["r_multiple"].to_numpy(float)
    pnl = df["pnl"].to_numpy(float)
    wins = pnl > 0
    winrate = wins.mean() * 100
    gp, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    pf = gp / gl if gl > 0 else float("inf")
    avg_win = r[wins].mean() if wins.any() else 0.0
    avg_loss = r[~wins].mean() if (~wins).any() else 0.0
    # longest losing streak
    streak = mx = 0
    for w in wins:
        streak = 0 if w else streak + 1
        mx = max(mx, streak)

    m = st.columns(6)
    m[0].metric("Trades", len(closed))
    m[1].metric("Trefferquote", f"{winrate:.0f}%", f"{int(wins.sum())}/{len(closed)}")
    m[2].metric("Erwartung/Trade", f"{r.mean():+.2f} R")
    m[3].metric("Profit-Faktor", "∞" if pf == float("inf") else f"{pf:.2f}")
    m[4].metric("Ø Gewinn/Verlust", f"{avg_win:+.2f}R / {avg_loss:+.2f}R")
    m[5].metric("Längste Verlustserie", f"{mx}")

    cL, cR = st.columns(2)
    with cL:
        st.caption("R-Verteilung (Gewinn/Verlust je Trade in Risiko-Einheiten)")
        try:
            import altair as alt
            rdf = pd.DataFrame({"R": r})
            hist = alt.Chart(rdf).mark_bar(color="#4c8dff").encode(
                x=alt.X("R:Q", bin=alt.Bin(maxbins=20), title="R-Vielfaches"),
                y=alt.Y("count()", title="Trades"))
            zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(
                color="#ff6b6b", strokeDash=[4, 4]).encode(x="x:Q")
            st.altair_chart(alt.layer(hist, zero), use_container_width=True)
        except Exception:
            st.bar_chart(pd.Series(r).round(1).value_counts().sort_index())
    with cR:
        st.caption("P&L nach Strategie / Coin")
        by_strat = (df.groupby("strategy")
                    .agg(Trades=("pnl", "size"), PnL=("pnl", "sum"),
                         Trefferquote=("pnl", lambda s: round((s > 0).mean() * 100)),
                         avgR=("r_multiple", "mean")).round(2)
                    .sort_values("PnL", ascending=False))
        eur = {"PnL": st.column_config.NumberColumn("P&L", format="%.2f €")}
        st.dataframe(by_strat, use_container_width=True, column_config=eur)
        by_coin = (df.groupby("symbol")
                   .agg(Trades=("pnl", "size"), PnL=("pnl", "sum"),
                        Trefferquote=("pnl", lambda s: round((s > 0).mean() * 100))).round(2)
                   .sort_values("PnL", ascending=False))
        st.dataframe(by_coin, use_container_width=True, column_config=eur)

    with st.expander(f"Alle Trades ({len(df)})"):
        show = df.copy()
        show["dauer_min"] = ((show["ts_close"] - show["ts_open"]) / 60000).round(0)
        show = show.sort_values("ts_close", ascending=False)[
            ["symbol", "strategy", "side", "entry", "exit", "pnl", "r_multiple", "reason", "dauer_min"]]
        st.dataframe(show, use_container_width=True, hide_index=True, column_config={
            "pnl": st.column_config.NumberColumn("P&L", format="%.2f €"),
            "r_multiple": st.column_config.NumberColumn("R", format="%.2f"),
        })


# US-reachable exchanges tried in order. Binance is geo-blocked on Streamlit
# Cloud (US); Kraken/KuCoin/OKX/Coinbase are reachable, so charts work there too.
CEX_EXCHANGES = ["binance", "kraken", "kucoin", "okx", "coinbase"]


@st.cache_data(ttl=120, show_spinner=False)
def _load_candles(symbol: str, timeframe: str, days: int):
    """Fetch real candles. On-chain via GeckoTerminal; CEX tries several
    US-reachable exchanges so charts also render on Streamlit Cloud. Fail-fast
    (max_retries=1) so a blocked exchange can't freeze the page. Cached 120s."""
    from core.utils import closed_bars

    def _finish(raw):
        df = closed_bars(raw, timeframe).tail(400).copy()
        df["time"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    if ":" in symbol:
        from data.dex_source import DexSource
        return _finish(DexSource(max_retries=1, backoff_base_sec=0.5)
                       .fetch_ohlcv(symbol, timeframe, days))

    from data.ccxt_source import CcxtSource
    base = symbol.split("/")[0]
    variants = list(dict.fromkeys([symbol, f"{base}/USD", f"{base}/USDT"]))
    last = None
    for ex in CEX_EXCHANGES:
        for sym in variants:
            try:
                raw = CcxtSource(ex, max_retries=1, backoff_base_sec=0.4).fetch_ohlcv(sym, timeframe, days)
                if raw is not None and len(raw):
                    return _finish(raw)
            except Exception as e:
                last = e
                continue
    raise last or RuntimeError(f"no candle source for {symbol}")


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

    # Entry (buy) and exit (sell) markers — cap to the most recent to avoid clutter.
    st_trades = sorted([t for t in trades if t["symbol"] == symbol],
                       key=lambda t: t.get("ts_close") or 0)[-80:]
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
    if READONLY:
        st.caption("Kurse via US-erreichbare Börsen (Binance→Kraken→KuCoin→OKX→Coinbase). "
                   "Falls ein Coin dort nicht handelbar ist, nutze die Chart-Links pro Coin.")
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
            try:
                cdf = _load_candles(sym, tf, days)
                cur = float(cdf["close"].iloc[-1])
                upnl = pos["qty"] * (cur - pos["entry"])  # long-only
                col = "#33d17a" if upnl >= 0 else "#ff6b6b"
                st.markdown(f'**Aktuell {cur:.6g} € · offener G/V '
                            f'<span style="color:{col}">{upnl:+,.2f} €</span>**',
                            unsafe_allow_html=True)
            except Exception:
                pass
            st.caption(f"Entry {pos['entry']:.6g} € · Stop {pos['stop']:.6g} €"
                       + (f" · TP {pos['tp']:.6g} €" if pos.get("tp") is not None else "")
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
        "Live-Paper (aktiv, echte 5m-Daten)": os.path.join("cloud", "live.db"),
        "CEX-Paper (echte ccxt-Daten)": os.path.join("cloud", "paper.db"),
        "On-Chain-Paper (echte GeckoTerminal-Daten)": os.path.join("cloud", "dex.db"),
    }
    # Include the env-configured DB if it's something else entirely.
    if DB_PATH not in candidates.values():
        candidates[f"Konfiguriert ({DB_PATH})"] = DB_PATH
    labels = list(candidates)
    default_idx = next((i for i, l in enumerate(labels) if candidates[l] == DB_PATH), 0)
    with st.sidebar:
        st.markdown("### Bot-Ansicht")
        st.caption("Alle sind Paper (simuliertes Geld) auf echten Marktdaten.")
        choice = st.radio("Datenquelle", labels, index=default_idx)
        path = candidates[choice]
        st.caption(f"DB: `{path}`" + ("" if os.path.exists(path) else "  · noch nicht angelegt"))
        st.markdown("### Live-Ansicht")
        auto = st.checkbox("Auto-Refresh (nur Live-Tab)", value=True)
        secs = st.slider("Alle N Sekunden", 5, 60, 15, disabled=not auto)
        st.caption("Aktualisiert nur den Live-Tab an Ort und Stelle — andere Tabs bleiben stehen.")
        with st.expander("💶 Steuer-Schätzung (keine Beratung)"):
            st.session_state["tax_rate"] = st.slider("Steuersatz %", 0, 45, 26) / 100.0
            st.session_state["tax_free"] = st.number_input(
                "Freigrenze €/Jahr", min_value=0, max_value=100000, value=1000, step=100)
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

    def _safe(fn):
        try:
            fn()
        except Exception as e:  # never let one tab blank the whole app
            st.error(f"Fehler in diesem Tab: {type(e).__name__}: {e}")

    tabs = st.tabs(["📈 Live", "🔎 Discover", "👁 Observe", "🏆 Ranking",
                    "🔬 Detail", "🗺 Heatmap", "📜 Audit"])
    with tabs[0]:
        _safe(lambda: tab_live(db_path, auto, secs)) if db else st.caption("Noch keine Daten.")
    with tabs[1]:
        _safe(tab_discover)
    with tabs[2]:
        _safe(tab_observe)
    with tabs[3]:
        _safe(lambda: tab_ranking(db)) if db else st.caption("Noch keine Daten.")
    with tabs[4]:
        _safe(lambda: tab_detail(db)) if db else st.caption("Noch keine Daten.")
    with tabs[5]:
        _safe(lambda: tab_heatmap(db)) if db else st.caption("Noch keine Daten.")
    with tabs[6]:
        _safe(lambda: tab_audit(db)) if db else st.caption("Noch keine Daten.")
    if db:
        db.close()


if __name__ == "__main__":
    main()

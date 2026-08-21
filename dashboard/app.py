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
def tab_live(db: Database) -> None:
    row = db.conn.execute("SELECT * FROM heartbeat WHERE id=1").fetchone()
    hb = dict(row) if row else {}
    eq = db.last_equity()
    positions = db.load_positions()
    trades = db.recent_trades(500)

    status = hb.get("status", "unknown")
    kind = "green" if status == "running" else ("amber" if status == "safe_hold" else "red")
    st.markdown(f"### Live Paper-Trader &nbsp; {_pill(status, kind)}", unsafe_allow_html=True)

    # KPIs
    init_eq = 10000.0
    wins = [t for t in trades if t["pnl"] > 0]
    wr = (len(wins) / len(trades) * 100.0) if trades else 0.0
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Equity (sim)", f"{eq:,.0f}" if eq is not None else "-",
              f"{(eq/init_eq-1)*100:+.2f}%" if eq else None)
    m2.metric("Open positions", len(positions))
    m3.metric("Closed trades", len(trades))
    m4.metric("Win rate", f"{wr:.0f}%")
    age = (time.time() * 1000 - hb["ts"]) / 1000 if hb.get("ts") else None
    m5.metric("Heartbeat age", f"{age:.0f}s" if age is not None else "-")

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

    _candles_with_markers(db, positions, trades)


def _candles_with_markers(db: Database, positions, trades) -> None:
    st.markdown("#### Candle chart with trade markers")
    try:
        import altair as alt
        from config.settings import Settings
        from core.utils import closed_bars
        from data.factory import build_data_source
    except Exception as e:
        st.caption(f"Candle chart unavailable: {e}")
        return
    symbols = sorted({t["symbol"] for t in trades} | {p["symbol"] for p in positions})
    if not symbols:
        st.caption("No symbol activity yet.")
        return
    sym = st.selectbox("Symbol", symbols)
    try:
        s = Settings.load()
        data = build_data_source(s)
        raw = data.fetch_ohlcv(sym, s.get("data.timeframe", "1h"), 30)
        df = closed_bars(raw, s.get("data.timeframe", "1h")).tail(300).copy()
        df["time"] = pd.to_datetime(df["timestamp"], unit="ms")
    except Exception as e:
        st.caption(f"Could not load candles for {sym}: {e}")
        return
    base = alt.Chart(df).encode(x=alt.X("time:T", title=None))
    rule = base.mark_rule().encode(y=alt.Y("low:Q", scale=alt.Scale(zero=False)), y2="high:Q")
    bar = base.mark_bar().encode(
        y="open:Q", y2="close:Q",
        color=alt.condition("datum.close >= datum.open", alt.value("#2ca02c"), alt.value("#d62728")))
    layers = [rule, bar]
    sym_trades = [t for t in trades if t["symbol"] == sym and t.get("ts_close")]
    if sym_trades:
        tm = pd.DataFrame(sym_trades)
        tm["time"] = pd.to_datetime(tm["ts_close"], unit="ms")
        markers = alt.Chart(tm).mark_point(size=90, filled=True).encode(
            x="time:T", y="exit:Q",
            color=alt.condition("datum.pnl >= 0", alt.value("#2ca02c"), alt.value("#d62728")),
            tooltip=["strategy", "symbol", "pnl", "r_multiple", "reason"])
        layers.append(markers)
    st.altair_chart(alt.layer(*layers).interactive(), use_container_width=True)


def tab_signals() -> None:
    st.markdown("### Signals & Watchlist")
    st.info("**Attention ≠ prediction.** This ranks how much activity a token has "
            "RIGHT NOW. By the time a coin trends, you are usually late. Every row links "
            "out so you can verify on RugCheck / GMGN / Axiom before risking anything. "
            "Refresh with `python cli.py scan`.")
    if not os.path.exists(WATCHLIST_PATH):
        st.caption(f"No `{WATCHLIST_PATH}` yet. Run `python cli.py scan` to generate it.")
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
    rows = []
    for t in tokens:
        f = t.get("features", {})
        lk = t.get("links", {})
        rows.append({
            "attention": t.get("attention"),
            "tradeable": "✅" if t.get("tradeable") else "⛔",
            "symbol": t.get("symbol"),
            "liq$": f.get("liquidity_usd"),
            "vol24$": f.get("volume_24h_usd"),
            "age_h": f.get("age_hours"),
            "flags": "; ".join(t.get("risk", {}).get("reasons", [])[:2]) or "-",
            "RugCheck": lk.get("rugcheck"), "GMGN": lk.get("gmgn"), "Axiom": lk.get("axiom"),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, column_config={
        "RugCheck": st.column_config.LinkColumn("RugCheck", display_text="check"),
        "GMGN": st.column_config.LinkColumn("GMGN", display_text="open"),
        "Axiom": st.column_config.LinkColumn("Axiom", display_text="observe"),
        "liq$": st.column_config.NumberColumn(format="$%d"),
        "vol24$": st.column_config.NumberColumn(format="$%d"),
    })
    n_ok = sum(1 for t in tokens if t.get("tradeable"))
    st.caption(f"{len(tokens)} tokens scanned · {n_ok} passed the rug filters. "
               "Most trending tokens fail — that is the honest reality, not a bug.")


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
        auto = st.checkbox("Auto-refresh (like MockApe)", value=True)
        secs = st.slider("Every N seconds", 5, 60, 15, disabled=not auto)
        if auto:
            try:
                from streamlit.components.v1 import html
                html(f"<script>setTimeout(function(){{window.parent.location.reload();}}, {secs*1000});</script>",
                     height=0)
            except Exception:
                pass
    return path


def main() -> None:
    st.set_page_config(page_title="Memecoin Paper Trader", layout="wide", page_icon="🎲")
    st.markdown(_CSS, unsafe_allow_html=True)
    st.title("🎲 Memecoin Paper-Trading Analysis")
    _banners()
    db_path = _pick_db_path()
    if not os.path.exists(db_path):
        st.info(f"No database yet at `{db_path}`. Run the matching bot "
                "(`ci-tick` for CEX, `dex-bot`/config_dex for on-chain) first.")
    db = Database(db_path) if os.path.exists(db_path) else None

    tabs = st.tabs(["📈 Live", "🔎 Signals", "👁 Observe", "🏆 Ranking",
                    "🔬 Detail", "🗺 Heatmap", "📜 Audit"])
    with tabs[0]:
        tab_live(db) if db else st.caption("No data yet.")
    with tabs[1]:
        tab_signals()
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

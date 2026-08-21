"""Streamlit dashboard for the memecoin paper trader (read-only capable).

Run locally:   streamlit run dashboard/app.py
Cloud (public, read-only):  set CLOUD_READONLY=1 and TRADING_DB=cloud/paper.db

Everything shown is SIMULATED. Live trading is locked. Memecoins are extremely
risky and mostly go to zero — nothing here is a prediction or advice.
"""
from __future__ import annotations

import os
import sys
import time

# Make the project importable when Streamlit runs this file directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from persistence.db import Database  # noqa: E402

READONLY = os.environ.get("CLOUD_READONLY", "0") == "1"
DB_PATH = os.environ.get("TRADING_DB", os.path.join("cloud", "paper.db"))


def _db() -> Database:
    return Database(DB_PATH)


def _banners() -> None:
    st.warning("**PAPER TRADING — SIMULATED MONEY ONLY.** Live trading is locked "
               "(`LiveTradingNotEnabled`). No real orders are ever placed.")
    st.error("**MEMECOIN RISK:** memecoins are extremely risky — most trend to zero, "
             "rugpulls are common, liquidity is thin and slippage is high. Short-term "
             "positive results are usually noise. This is not investment advice.")


def _kill_switch_controls(db: Database) -> None:
    if READONLY:
        st.info("Read-only cloud view — control buttons are hidden.")
        return
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("⏸ Stop (safe)"):
        db.set_control("command", "stop"); st.success("Stop requested.")
    if c2.button("▶ Run"):
        db.set_control("command", "run"); st.success("Run requested.")
    if c3.button("Reset daily breaker"):
        db.set_control("reset_breaker", "1"); st.success("Breaker reset requested.")
    if c4.button("Clear kill switch"):
        db.set_control("kill_tripped", "0"); st.success("Kill switch cleared.")


def tab_live(db: Database) -> None:
    st.subheader("Live Paper-Trader")
    row = db.conn.execute("SELECT * FROM heartbeat WHERE id=1").fetchone()
    hb = dict(row) if row else {}
    eq = db.last_equity()
    positions = db.load_positions()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Status", hb.get("status", "unknown"))
    m2.metric("Equity (sim)", f"{eq:,.2f}" if eq is not None else "-")
    m3.metric("Open positions", len(positions))
    age = (time.time() * 1000 - hb["ts"]) / 1000 if hb.get("ts") else None
    m4.metric("Heartbeat age", f"{age:.0f}s" if age is not None else "-")

    _kill_switch_controls(db)

    st.markdown("**Equity curve (simulated)**")
    curve = db.equity_curve(5000)
    if curve:
        ec = pd.DataFrame(curve, columns=["ts", "equity"])
        ec["time"] = pd.to_datetime(ec["ts"], unit="ms")
        st.line_chart(ec.set_index("time")["equity"])
    else:
        st.caption("No equity points yet.")

    st.markdown("**Open positions**")
    st.dataframe(pd.DataFrame(positions) if positions else pd.DataFrame(columns=["strategy", "symbol"]))

    st.markdown("**Activity feed (recent audit)**")
    st.dataframe(pd.DataFrame(db.recent_audit(50)))

    # Candle chart with buy/sell markers for a chosen symbol (best-effort, uses Altair).
    _candles_with_markers(db, positions)


def _candles_with_markers(db: Database, positions) -> None:
    try:
        import altair as alt
        from config.settings import Settings
        from core.utils import closed_bars
        from data.factory import build_data_source
    except Exception as e:  # pragma: no cover
        st.caption(f"Candle chart unavailable: {e}")
        return

    trades = db.recent_trades(200)
    symbols = sorted({t["symbol"] for t in trades} | {p["symbol"] for p in positions})
    if not symbols:
        st.caption("No symbol activity yet for a candle chart.")
        return
    sym = st.selectbox("Candle chart symbol", symbols)
    try:
        s = Settings.load()
        data = build_data_source(s)
        raw = data.fetch_ohlcv(sym, s.get("data.timeframe", "1h"), 30)
        df = closed_bars(raw, s.get("data.timeframe", "1h")).tail(300).copy()
        df["time"] = pd.to_datetime(df["timestamp"], unit="ms")
    except Exception as e:
        st.caption(f"Could not load candles for {sym}: {e}")
        return

    base = alt.Chart(df).encode(x="time:T")
    rule = base.mark_rule().encode(y="low:Q", y2="high:Q")
    bar = base.mark_bar().encode(
        y="open:Q", y2="close:Q",
        color=alt.condition("datum.close >= datum.open",
                            alt.value("#2ca02c"), alt.value("#d62728")))
    layers = [rule, bar]

    sym_trades = [t for t in trades if t["symbol"] == sym and t.get("ts_close")]
    if sym_trades:
        tm = pd.DataFrame(sym_trades)
        tm["time"] = pd.to_datetime(tm["ts_close"], unit="ms")
        buys = base  # entries approximated by exit markers here for simplicity
        markers = alt.Chart(tm).mark_point(size=80, filled=True).encode(
            x="time:T", y="exit:Q",
            color=alt.condition("datum.pnl >= 0", alt.value("#2ca02c"), alt.value("#d62728")),
            tooltip=["strategy", "symbol", "pnl", "r_multiple", "reason"])
        layers.append(markers)
    st.altair_chart(alt.layer(*layers).interactive(), use_container_width=True)


def tab_ranking(db: Database) -> None:
    st.subheader("Ranking (latest evaluations)")
    evals = db.latest_evaluations(500)
    if not evals:
        st.caption("No evaluations yet. Run `python cli.py rank --db`.")
        return
    df = pd.DataFrame(evals)
    # Keep the newest row per (strategy, symbol).
    df = df.sort_values("id").drop_duplicates(["strategy", "symbol"], keep="last")
    df = df.sort_values("score", ascending=False)
    st.dataframe(df[["light", "score", "strategy", "symbol", "expectancy_r",
                     "n_trades", "mean_efficiency", "ruin_prob"]])


def tab_detail(db: Database) -> None:
    st.subheader("Detail (score decomposition)")
    evals = db.latest_evaluations(500)
    if not evals:
        st.caption("No evaluations yet.")
        return
    import json
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
    st.json({k: v for k, v in extra.items() if k not in ("subscores", "warnings", "params")})


def tab_portfolio(db: Database) -> None:
    st.subheader("Portfolio")
    st.caption("Diversification lowers drawdown and smooths equity; it does not create "
               "winners. If the combos have no edge, the portfolio has no edge.")
    evals = db.latest_evaluations(500)
    if not evals:
        st.caption("No evaluations yet.")
        return
    df = pd.DataFrame(evals).sort_values("id").drop_duplicates(["strategy", "symbol"], keep="last")
    st.dataframe(df[["light", "score", "strategy", "symbol"]].sort_values("score", ascending=False))


def tab_heatmap(db: Database) -> None:
    st.subheader("Heatmap (score by strategy x symbol)")
    evals = db.latest_evaluations(1000)
    if not evals:
        st.caption("No evaluations yet.")
        return
    df = pd.DataFrame(evals).sort_values("id").drop_duplicates(["strategy", "symbol"], keep="last")
    pivot = df.pivot_table(index="strategy", columns="symbol", values="score", aggfunc="last")
    st.dataframe(pivot.style.background_gradient(cmap="RdYlGn", vmin=0, vmax=100))


def tab_audit(db: Database) -> None:
    st.subheader("Audit log")
    st.dataframe(pd.DataFrame(db.recent_audit(300)))


def main() -> None:
    st.set_page_config(page_title="Memecoin Paper Trader", layout="wide")
    st.title("Memecoin Paper-Trading Analysis")
    _banners()
    if not os.path.exists(DB_PATH):
        st.info(f"No database yet at `{DB_PATH}`. Run `python cli.py ci-tick` or `serve` first.")
        return
    db = _db()
    tabs = st.tabs(["Live", "Ranking", "Detail", "Portfolio", "Heatmap", "Audit"])
    with tabs[0]:
        tab_live(db)
    with tabs[1]:
        tab_ranking(db)
    with tabs[2]:
        tab_detail(db)
    with tabs[3]:
        tab_portfolio(db)
    with tabs[4]:
        tab_heatmap(db)
    with tabs[5]:
        tab_audit(db)
    db.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Command-line entry point for the memecoin paper-trading analysis tool.

Everything here trades SIMULATED money. Live trading is locked
(execution/live.py). Memecoins are extremely risky and mostly go to zero —
nothing this tool prints is a prediction or investment advice.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional

import yaml

import strategies  # noqa: F401  (register all strategies)
from config.settings import Settings, build_engine_config
from execution.paper import Combo

DEFAULT_DB = os.path.join("state", "paper.db")
CLOUD_DB = os.path.join("cloud", "paper.db")
DEFAULT_ACTIVE_STRATEGIES = ["ema_crossover", "supertrend", "donchian_breakout"]


# ----------------------------------------------------------------------------
def _resolve_db(default: str) -> str:
    path = os.environ.get("TRADING_DB", default)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


def _load_combos(settings: Settings, active_path: str = "active_combos.yaml") -> List[Combo]:
    if os.path.exists(active_path):
        with open(active_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        combos = []
        for c in data.get("combos", []):
            combos.append(Combo(c["strategy"], c["symbol"], c.get("params", {}) or {}))
        if combos:
            return combos
    # Fallback: universe x default strategies.
    strat_list = settings.get("active.strategies", DEFAULT_ACTIVE_STRATEGIES)
    return [Combo(s, sym, {}) for sym in settings.universe for s in strat_list]


def _banner() -> None:
    print("=" * 70)
    print(" MEMECOIN PAPER-TRADING ANALYSIS TOOL  --  SIMULATED MONEY ONLY")
    print(" Live trading is locked. Memecoins mostly go to zero. Not advice.")
    print("=" * 70)


# ----------------------------------------------------------------------------
def cmd_doctor(args) -> int:
    _banner()
    ok = True
    print("\n[1] Python & core deps")
    print(f"    python {sys.version.split()[0]}")
    for mod in ("pandas", "numpy", "yaml"):
        try:
            __import__(mod)
            print(f"    ok   {mod}")
        except Exception as e:  # pragma: no cover
            ok = False
            print(f"    FAIL {mod}: {e}")
    for mod in ("ccxt", "requests", "streamlit"):
        try:
            __import__(mod)
            print(f"    ok   {mod} (optional)")
        except Exception:
            print(f"    warn {mod} not installed (optional; needed for some features)")

    print("\n[2] Config")
    try:
        s = Settings.load(args.config)
        problems = s.validate()
        if problems:
            ok = False
            for p in problems:
                print(f"    FAIL {p}")
        else:
            print(f"    ok   config valid (mode={s.mode}, {len(s.universe)} symbols)")
    except Exception as e:
        ok = False
        print(f"    FAIL could not load config: {e}")
        return 0 if args.soft else 2

    print("\n[3] Strategies")
    from strategies.base import available_strategies
    names = sorted(available_strategies())
    print(f"    ok   {len(names)} registered: {', '.join(names)}")

    print("\n[4] Engine self-test (synthetic)")
    try:
        from backtest.engine import run_backtest
        from strategies.base import build_strategy
        from tests.synth import trend_up
        r = run_backtest(build_strategy("ema_crossover", {}), trend_up(300),
                         build_engine_config(s))
        print(f"    ok   engine ran, equity_curve={len(r.equity_curve)} bars")
    except Exception as e:
        ok = False
        print(f"    FAIL engine self-test: {e}")

    print("\n[5] Live-trading lock")
    try:
        from execution.live import LiveBroker, LiveTradingNotEnabled
        try:
            LiveBroker()
            ok = False
            print("    FAIL live broker did NOT refuse (should be locked)")
        except LiveTradingNotEnabled:
            print("    ok   live trading correctly locked")
    except Exception as e:
        ok = False
        print(f"    FAIL live lock import: {e}")

    if args.data:
        print("\n[6] Data source (real fetch)")
        try:
            from data.factory import build_data_source
            src = build_data_source(s)
            sym = s.universe[0] if s.universe else "DOGE/USDT"
            df = src.fetch_ohlcv(sym, s.get("data.timeframe", "1h"), 5)
            print(f"    ok   fetched {len(df)} real bars for {sym}")
        except Exception as e:
            print(f"    warn data fetch failed ({e}) — will skip combos at runtime, not fake data")

    print("\n" + ("DOCTOR: all critical checks passed." if ok else "DOCTOR: problems found (see FAIL above)."))
    return 0 if ok else 1


def _fetch_and_eval(s: Settings, combos: List[Combo]) -> List[Any]:
    from backtest.evaluation import evaluate_combo
    from data.base import DataUnavailable
    from data.factory import build_data_source
    data = build_data_source(s)
    cfg = build_engine_config(s)
    tf = s.get("data.timeframe", "1h")
    lookback = int(s.get("data.lookback_days", 180))
    evals = []
    # Cache raw fetches per symbol to avoid redundant API calls.
    raw_cache: Dict[str, Any] = {}
    for c in combos:
        if c.symbol not in raw_cache:
            try:
                raw_cache[c.symbol] = data.fetch_ohlcv(c.symbol, tf, lookback)
            except DataUnavailable as e:
                print(f"    skip {c.symbol}: {e}")
                raw_cache[c.symbol] = None
        raw = raw_cache[c.symbol]
        if raw is None:
            continue
        ev = evaluate_combo(c.strategy, c.symbol, raw, cfg, s, tf)
        if ev is None:
            print(f"    skip {c.strategy}@{c.symbol}: insufficient real history")
            continue
        evals.append(ev)
    return evals


def cmd_rank(args) -> int:
    _banner()
    s = Settings.load(args.config)
    combos = _load_combos(s, args.active)
    if args.all_strategies:
        from strategies.base import available_strategies
        combos = [Combo(st, sym, {}) for sym in s.universe for st in available_strategies()]
    print(f"\nEvaluating {len(combos)} combos on REAL data (skipping any that fail data checks)...\n")
    evals = _fetch_and_eval(s, combos)
    evals.sort(key=lambda e: e.score, reverse=True)

    print(f"{'rank':<5}{'light':<8}{'score':>6}  {'strategy':<22}{'symbol':<12}"
          f"{'expR':>7}{'trades':>7}{'maxDD':>7}{'WFeff':>7}{'ruin':>7}")
    print("-" * 100)
    for i, e in enumerate(evals[: args.limit], 1):
        print(f"{i:<5}{e.light:<8}{e.score:>6.1f}  {e.strategy:<22}{e.symbol:<12}"
              f"{e.expectancy_r:>7.3f}{e.n_trades:>7}{e.max_drawdown:>7.2%}"
              f"{e.mean_efficiency:>7.2f}{e.ruin_prob:>7.2%}")

    if args.db:
        from persistence.db import Database
        db = Database(_resolve_db(DEFAULT_DB))
        for e in evals:
            db.record_evaluation({"ts": int(time.time() * 1000), **e.as_record()})
        db.close()
    print("\nReminder: green is a descriptive score of PAST simulated behaviour, not a "
          "prediction. Memecoins mostly go to zero; short positive results are usually noise.")
    return 0


def cmd_backtest(args) -> int:
    _banner()
    s = Settings.load(args.config)
    combos = [Combo(args.strategy, args.symbol, {})]
    evals = _fetch_and_eval(s, combos)
    if not evals:
        print("No evaluation produced (data unavailable or too short). Nothing faked.")
        return 1
    e = evals[0]
    print(f"\n{e.strategy} @ {e.symbol}")
    print(f"  score            {e.score:.1f}  ({e.light})")
    print(f"  sub-scores       {e.subscores}")
    print(f"  expectancy (R)   {e.expectancy_r:.3f}")
    print(f"  trades           {e.n_trades}")
    print(f"  total return     {e.total_return:.2%}  (simulated)")
    print(f"  max drawdown     {e.max_drawdown:.2%}")
    print(f"  WF efficiency    {e.mean_efficiency:.2f}")
    print(f"  MC ruin prob     {e.ruin_prob:.2%}")
    print("  warnings:")
    for w in e.warnings:
        print(f"    - {w}")
    return 0


def cmd_export_active(args) -> int:
    s = Settings.load(args.config)
    combos = _load_combos(s, args.active)
    if args.all_strategies:
        from strategies.base import available_strategies
        combos = [Combo(st, sym, {}) for sym in s.universe for st in available_strategies()]
    print(f"Evaluating {len(combos)} combos to select active set (min score {args.min_score})...")
    evals = _fetch_and_eval(s, combos)
    selected = [e for e in evals if e.score >= args.min_score]
    selected.sort(key=lambda e: e.score, reverse=True)
    out = {"generated_ts": int(time.time() * 1000),
           "min_score": args.min_score,
           "note": "Descriptive selection from simulated backtests. Not advice. Memecoins mostly go to zero.",
           "combos": [{"strategy": e.strategy, "symbol": e.symbol, "params": e.params,
                       "score": e.score} for e in selected]}
    with open(args.out, "w", encoding="utf-8") as fh:
        yaml.safe_dump(out, fh, sort_keys=False)
    print(f"Wrote {len(selected)} active combos to {args.out}")
    return 0


def cmd_serve(args) -> int:
    _banner()
    s = Settings.load(args.config)
    problems = s.validate()
    if problems:
        print("Refusing to serve — config problems:")
        for p in problems:
            print(f"  - {p}")
        return 2
    combos = _load_combos(s, args.active)
    from execution.serve import AlreadyRunning, serve
    db_path = _resolve_db(DEFAULT_DB)
    print(f"Serving {len(combos)} combos, db={db_path}, tick={args.tick}s. Ctrl-C to stop.")
    try:
        serve(s, combos, db_path, tick_interval_sec=args.tick,
              adjust_interval_sec=args.adjust, max_ticks=args.max_ticks)
    except AlreadyRunning as e:
        print(f"Not started: {e}")
        return 3
    return 0


def cmd_ci_tick(args) -> int:
    """One paper tick for CI/cloud: persist to cloud db, write status report, checkpoint."""
    s = Settings.load(args.config)
    combos = _load_combos(s, args.active)
    from data.factory import build_data_source
    from persistence.db import Database
    db_path = _resolve_db(CLOUD_DB)
    db = Database(db_path)
    db.set_control("command", "run")
    data = build_data_source(s)
    from execution.paper import PaperTrader
    trader = PaperTrader(s, data, db, combos)
    trader.recover_state()
    result = trader.tick()
    _write_status_report(db, s, result, path=getattr(args, "report", "BOT_STATUS_REPORT.md"))
    db.checkpoint()
    db.close()
    print(f"ci-tick done: {result}")
    return 0


def _write_status_report(db, s: Settings, result: Dict[str, Any],
                         path: str = "BOT_STATUS_REPORT.md") -> None:
    positions = db.load_positions()
    trades = db.recent_trades(10)
    lines = [
        "# Bot Status Report",
        "",
        "**Paper trading — simulated money only. Live trading is locked. "
        "Memecoins are extremely risky and mostly go to zero. This is not advice "
        "and not a prediction.**",
        "",
        f"- Generated (UTC): {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}",
        f"- Status: **{result.get('status')}**",
        f"- Equity (simulated): {result.get('equity', 0):.2f}",
        f"- Cash: {result.get('cash', 0):.2f}",
        f"- Open positions: {result.get('open_positions', 0)}",
        f"- Combos processed / skipped: {result.get('processed', 0)} / {result.get('skipped', 0)}",
        f"- Circuit breaker: {result.get('breaker')}  |  Kill switch: {result.get('kill')}",
        "",
        "## Open positions",
    ]
    if positions:
        lines.append("| strategy | symbol | side | qty | entry | stop |")
        lines.append("|---|---|---|---|---|---|")
        for p in positions:
            lines.append(f"| {p['strategy']} | {p['symbol']} | {p['side']} | "
                         f"{p['qty']:.4g} | {p['entry']:.6g} | {p['stop']:.6g} |")
    else:
        lines.append("_none_")
    lines += ["", "## Last trades (simulated)"]
    if trades:
        lines.append("| strategy | symbol | pnl | R | reason |")
        lines.append("|---|---|---|---|---|")
        for t in trades:
            lines.append(f"| {t['strategy']} | {t['symbol']} | {t['pnl']:.2f} | "
                         f"{t['r_multiple']:.2f} | {t['reason']} |")
    else:
        lines.append("_none yet_")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def cmd_stress(args) -> int:
    """Million-trade stress test on a combo's realised R distribution."""
    _banner()
    s = Settings.load(args.config)
    from backtest.engine import run_backtest
    from core.utils import closed_bars
    from data.base import DataUnavailable
    from data.factory import build_data_source
    from optimize.stress import stress_test
    from strategies.base import build_strategy
    data = build_data_source(s)
    cfg = build_engine_config(s)
    tf = s.get("data.timeframe", "1h")
    try:
        raw = data.fetch_ohlcv(args.symbol, tf, int(s.get("data.lookback_days", 180)))
    except DataUnavailable as e:
        print(f"Data unavailable for {args.symbol}: {e} (nothing faked)")
        return 1
    df = closed_bars(raw, tf)
    df.attrs["symbol"] = args.symbol
    res = run_backtest(build_strategy(args.strategy, {}), df, cfg)
    r = [t.r_multiple for t in res.trades]
    if not r:
        print("No trades in the backtest sample — cannot stress-test an empty distribution.")
        return 1
    out = stress_test(r, n_trades=args.n, risk_per_trade=cfg.risk_per_trade)
    print(f"\nStress test ({args.n:,} resampled trades from {len(r)} real ones):")
    print(f"  worst drawdown     {out.worst_drawdown:.2%}")
    print(f"  prob. ruin         {out.prob_ruin:.0%}")
    print(f"  1st-pct equity x    {out.p01_equity_multiple:.3f}")
    print(f"  final return       {out.final_return:.2%}")
    print(f"\n  {out.note}")
    return 0


def cmd_optimize(args) -> int:
    _banner()
    s = Settings.load(args.config)
    from backtest.evaluation import PARAM_GRIDS
    from core.utils import closed_bars
    from data.base import DataUnavailable
    from data.factory import build_data_source
    from optimize.optimizer import optimize
    data = build_data_source(s)
    cfg = build_engine_config(s)
    tf = s.get("data.timeframe", "1h")
    try:
        raw = data.fetch_ohlcv(args.symbol, tf, int(s.get("data.lookback_days", 180)))
    except DataUnavailable as e:
        print(f"Data unavailable for {args.symbol}: {e} (nothing faked)")
        return 1
    df = closed_bars(raw, tf)
    df.attrs["symbol"] = args.symbol
    grid = PARAM_GRIDS.get(args.strategy, {})
    r = optimize(args.strategy, df, cfg, grid,
                 folds=int(s.get("validation.walkforward.folds", 4)),
                 wf_efficiency_min=float(s.get("optimize.wf_efficiency_min", 0.5)),
                 min_trades=int(s.get("optimize.min_trades", 20)))
    print(f"\nOptimize {args.strategy}@{args.symbol}: "
          f"{'ACCEPTED' if r.accepted else 'REJECTED'}")
    print(f"  reason           {r.reason}")
    print(f"  WF efficiency    {r.mean_efficiency:.2f}")
    print(f"  OOS trades       {r.oos_trades}")
    print(f"  OOS expectancy R {r.oos_expectancy_r:.3f}")
    print(f"  params           {r.params}")
    if not r.accepted:
        print("\n  Honest result: no validated parameters. We do NOT ship an in-sample fit.")
    return 0


def cmd_scan(args) -> int:
    """Scan currently-active on-chain memecoins: attention signal + rug filters.

    Attention = current activity, NOT a prediction. Every token gets a link to
    verify on RugCheck/GMGN/Axiom before you ever risk real money.
    """
    _banner()
    from data.memecoin_filters import (FilterConfig, fetch_goplus_solana,
                                        fetch_rugcheck, merge_metadata)
    from data.signals import build_watchlist, fetch_dexscreener_boosted
    print(f"\nScanning boosted {args.chain} tokens (attention + rug filters)... "
          "(real data; best-effort)\n")
    feats = fetch_dexscreener_boosted(args.chain, limit=args.limit)
    if not feats:
        print("No live token data returned (network/rate-limit). Nothing faked.")
        return 1
    metas = {}
    if not args.no_rugcheck and args.chain == "solana":
        for f in feats:
            rc = fetch_rugcheck(f.mint)
            gp = fetch_goplus_solana(f.mint) if args.goplus else None
            metas[f.mint] = merge_metadata(rc, gp)
    cfg = FilterConfig()
    wl = build_watchlist(feats, metas, cfg, tradeable_only=args.tradeable_only)

    print(f"{'att':>4}  {'ok':>3}  {'symbol':<12}{'liq$':>12}{'vol24$':>14}  flags")
    print("-" * 90)
    for s in wl[: args.limit]:
        flags = ",".join(s.risk.reasons[:2]) if s.risk.reasons else "-"
        ok = "yes" if s.tradeable else "NO"
        print(f"{s.attention:>4.0f}  {ok:>3}  {s.symbol:<12}"
              f"{s.features['liquidity_usd']:>12,.0f}{s.features['volume_24h_usd']:>14,.0f}  {flags[:44]}")

    if args.out:
        payload = {"generated_ts": int(time.time() * 1000),
                   "disclaimer": ("Attention = current activity, NOT a prediction. Most "
                                  "memecoins go to zero. Verify on RugCheck/GMGN/Axiom. "
                                  "This tool never places real orders."),
                   "tokens": [s.as_dict() for s in wl]}
        with open(args.out, "w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, sort_keys=False, allow_unicode=True)
        print(f"\nWrote {len(wl)} tokens to {args.out}")
    print("\nReminder: 'attention' ranks buzz, not future price. By the time a coin trends "
          "you are usually late. Verify every token yourself before risking anything.")
    return 0


def cmd_dex_combos(args) -> int:
    """Turn the tradeable watchlist into DEX paper-trading combos (network:pool)."""
    if not os.path.exists(args.watchlist):
        print(f"No {args.watchlist}. Run `python cli.py scan --tradeable-only` first.")
        return 1
    data = yaml.safe_load(open(args.watchlist, encoding="utf-8")) or {}
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    combos = []
    seen = set()
    for t in data.get("tokens", []):
        if args.tradeable_only and not t.get("tradeable"):
            continue
        pool = (t.get("features") or {}).get("pool_address")
        chain = t.get("chain", "solana")
        if not pool:
            continue
        symbol = f"{chain}:{pool}"
        if symbol in seen:
            continue
        seen.add(symbol)
        for st in strategies:
            combos.append({"strategy": st, "symbol": symbol, "params": {},
                           "token": t.get("symbol")})
    out = {"generated_ts": int(time.time() * 1000),
           "note": ("On-chain DEX paper-trading combos (simulated money). Short on-chain "
                    "history means many will be skipped by the data checks - intended."),
           "combos": combos}
    with open(args.out, "w", encoding="utf-8") as fh:
        yaml.safe_dump(out, fh, sort_keys=False, allow_unicode=True)
    print(f"Wrote {len(combos)} DEX combos ({len(seen)} tokens x {len(strategies)} strategies) "
          f"to {args.out}")
    print(f"Run: python cli.py --config config/config_dex.yaml serve --active {args.out}")
    return 0


def cmd_advise(args) -> int:
    """Free local advisor: turn the bot's own numbers into a paper-only recommendation."""
    _banner()
    from core.advisor import advise, ollama_summary
    from data.memecoin_filters import FilterVerdict
    if not os.path.exists(args.watchlist):
        print(f"No {args.watchlist}. Run `python cli.py scan` first.")
        return 1
    data = yaml.safe_load(open(args.watchlist, encoding="utf-8")) or {}
    tokens = data.get("tokens", [])[: args.limit]
    print(f"\n{'action':<16}{'conf':>5}  {'symbol':<12} reasons")
    print("-" * 90)
    for t in tokens:
        rv = t.get("risk", {})
        verdict = FilterVerdict(passed=rv.get("passed", True), reasons=rv.get("reasons", []),
                                checked=rv.get("checked", 0))
        adv = advise(rug_verdict=verdict, attention=t.get("attention"))
        print(f"{adv.action:<16}{adv.confidence:>5.2f}  {t.get('symbol',''):<12} "
              f"{'; '.join(adv.reasons[:2])[:52]}")
        if args.ollama:
            txt = ollama_summary(adv, context=f"token {t.get('symbol')}", model=args.model)
            if txt:
                print(f"    LLM: {txt}")
    print("\n" + advise().disclaimer)
    return 0


def cmd_status(args) -> int:
    from persistence.db import Database
    db = Database(_resolve_db(DEFAULT_DB))
    row = db.conn.execute("SELECT * FROM heartbeat WHERE id=1").fetchone()
    print("Heartbeat:", dict(row) if row else "none")
    print("Equity:", db.last_equity())
    print("Open positions:", len(db.load_positions()))
    db.close()
    return 0


def cmd_control(args) -> int:
    from persistence.db import Database
    db = Database(_resolve_db(DEFAULT_DB))
    if args.stop:
        db.set_control("command", "stop"); print("command=stop set")
    if args.run:
        db.set_control("command", "run"); print("command=run set")
    if args.reset_breaker:
        db.set_control("reset_breaker", "1"); print("reset_breaker requested")
    if args.reset_kill:
        db.set_control("kill_tripped", "0"); print("kill switch cleared")
    db.close()
    return 0


# ----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memebot", description="Memecoin paper-trading analysis tool (simulated money only).")
    p.add_argument("--config", default=None, help="path to config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="self-test the installation")
    d.add_argument("--data", action="store_true", help="also test a real data fetch")
    d.add_argument("--soft", action="store_true", help="always exit 0")
    d.set_defaults(func=cmd_doctor)

    r = sub.add_parser("rank", help="evaluate & rank combos on real data")
    r.add_argument("--limit", type=int, default=30)
    r.add_argument("--active", default="active_combos.yaml")
    r.add_argument("--all-strategies", action="store_true")
    r.add_argument("--db", action="store_true", help="persist evaluations to db")
    r.set_defaults(func=cmd_rank)

    b = sub.add_parser("backtest", help="evaluate a single strategy/symbol")
    b.add_argument("--strategy", required=True)
    b.add_argument("--symbol", required=True)
    b.set_defaults(func=cmd_backtest)

    e = sub.add_parser("export-active", help="write active_combos.yaml above a score threshold")
    e.add_argument("--min-score", type=float, default=55.0)
    e.add_argument("--out", default="active_combos.yaml")
    e.add_argument("--active", default="active_combos.yaml")
    e.add_argument("--all-strategies", action="store_true")
    e.set_defaults(func=cmd_export_active)

    sv = sub.add_parser("serve", help="run the paper trader continuously")
    sv.add_argument("--active", default="active_combos.yaml")
    sv.add_argument("--tick", type=float, default=60.0)
    sv.add_argument("--adjust", type=float, default=1800.0)
    sv.add_argument("--max-ticks", type=int, default=None)
    sv.set_defaults(func=cmd_serve)

    ci = sub.add_parser("ci-tick", help="one paper tick for CI/cloud")
    ci.add_argument("--active", default="active_combos.yaml")
    ci.add_argument("--report", default="BOT_STATUS_REPORT.md")
    ci.set_defaults(func=cmd_ci_tick)

    stx = sub.add_parser("stress", help="million-trade risk stress test on a combo")
    stx.add_argument("--strategy", required=True)
    stx.add_argument("--symbol", required=True)
    stx.add_argument("--n", type=int, default=1_000_000)
    stx.set_defaults(func=cmd_stress)

    op = sub.add_parser("optimize", help="walk-forward optimize with overfitting guard")
    op.add_argument("--strategy", required=True)
    op.add_argument("--symbol", required=True)
    op.set_defaults(func=cmd_optimize)

    sc = sub.add_parser("scan", help="scan active on-chain memecoins (attention + rug filters)")
    sc.add_argument("--chain", default="solana")
    sc.add_argument("--limit", type=int, default=25)
    sc.add_argument("--tradeable-only", action="store_true", help="only tokens passing rug filters")
    sc.add_argument("--no-rugcheck", action="store_true", help="skip RugCheck (faster, fewer checks)")
    sc.add_argument("--goplus", action="store_true", help="also query GoPlus security")
    sc.add_argument("--out", default="watchlist.yaml")
    sc.set_defaults(func=cmd_scan)

    dc = sub.add_parser("dex-combos", help="build DEX paper-trading combos from the watchlist")
    dc.add_argument("--watchlist", default="watchlist.yaml")
    dc.add_argument("--out", default="active_combos_dex.yaml")
    dc.add_argument("--strategies", default="donchian_breakout,supertrend,ema_crossover")
    dc.add_argument("--tradeable-only", action="store_true", default=True)
    dc.set_defaults(func=cmd_dex_combos)

    ad = sub.add_parser("advise", help="free local advisor over the watchlist (paper only)")
    ad.add_argument("--watchlist", default="watchlist.yaml")
    ad.add_argument("--limit", type=int, default=25)
    ad.add_argument("--ollama", action="store_true", help="phrase via a free local Ollama model")
    ad.add_argument("--model", default="llama3.2")
    ad.set_defaults(func=cmd_advise)

    st = sub.add_parser("status", help="print current status")
    st.set_defaults(func=cmd_status)

    co = sub.add_parser("control", help="send control commands")
    co.add_argument("--stop", action="store_true")
    co.add_argument("--run", action="store_true")
    co.add_argument("--reset-breaker", action="store_true")
    co.add_argument("--reset-kill", action="store_true")
    co.set_defaults(func=cmd_control)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except FileNotFoundError as e:
        print(f"\nError: file not found — {e}. Check your paths / config.")
        return 1
    except Exception as e:  # friendly, not a raw stacktrace
        print(f"\nSomething went wrong: {type(e).__name__}: {e}")
        print("This is a paper tool; no real money is involved. Run `doctor` to self-check,")
        print("or re-run with the environment variable MEMEBOT_TRACE=1 for a full traceback.")
        if os.environ.get("MEMEBOT_TRACE") == "1":
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())

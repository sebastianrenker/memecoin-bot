# Memecoin Paper-Trading Analysis Tool

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Mode](https://img.shields.io/badge/mode-paper--only-orange)
![Live trading](https://img.shields.io/badge/live%20trading-locked-red)

> A learning and analysis tool for memecoin strategies — real data, honest backtests, simulated money only.

## Overview

A **learning and analysis** tool for memecoin trading strategies that trades
**simulated money only**. It fetches **real** market data, backtests strategies
honestly (no look-ahead), validates them (walk-forward + Monte-Carlo + regime),
and paper-trades them continuously with strict risk controls.

> ⚠️ **Not financial advice. No predictions. Simulated money only.**
> Live trading is intentionally **locked** (`execution/live.py` raises
> `LiveTradingNotEnabled`). Memecoins are **extremely** risky: most trend to
> zero, rugpulls are common, liquidity is thin and slippage is high. A positive
> short-term paper result is almost always **noise**, not an edge.

This tool quantifies **risk** and describes **past simulated behaviour**. It does
**not** predict the future and there is **no "guaranteed profitable" switch**.

## Features

- **Real data only** (`data.require_real: true`) via [ccxt](https://github.com/ccxt/ccxt)
  (real OHLCV) and an optional on-chain DEX adapter (GeckoTerminal). If data can't
  be fetched, the combination is **skipped — never faked**.
- **Honest backtest engine**: signal on bar *t* executes at the **open of t+1**
  (no look-ahead); stop before take-profit; fees + slippage per side; leverage
  capped; too-tight stops rejected (not widened); bar debounce after exits.
- **Validation**: walk-forward (OOS scoring), Monte-Carlo bootstrap (CI + ruin
  probability), regime analysis, and a transparent **"works-now" score** with a
  traffic light and warnings.
- **15 strategies**, indicators implemented from scratch (pandas/numpy);
  mean-reversion **down-weighted** for memecoins by design.
- **Risk management**: 1% risk/trade, max open positions, daily-loss circuit
  breaker, total-drawdown kill switch, mandatory stops, one position per (strategy, symbol).
- **On-chain scan + rug filters**: live DexScreener data enriched with RugCheck /
  GoPlus; rejects mint/freeze authority, unlocked LP, honeypots, holder
  concentration, dust liquidity, brand-new launches. **Attention ≠ prediction.**
- **Local, transparent advisor** (`advise`): turns the bot's own numbers into
  `avoid` / `watch` / `paper_consider` — never a real-money order; a failed rug
  check overrides everything.
- **Persistence & ops**: SQLite (WAL) with full state recovery; controllable
  `serve` loop; Streamlit dashboard; free cloud deploy via GitHub Actions.

## Architecture

```
core/        types, indicators (from scratch), timeframe + closed_bars guard
strategies/  15 pluggable, parametrised strategies + registry/factory
data/        ccxt (real OHLCV), DEX (GeckoTerminal), cache, discovery, filters
backtest/    event engine, walk-forward, monte-carlo, regime, evaluation
stats/       metrics + the transparent works-now score
risk/        risk manager (breaker, kill switch, min-stop, debounce)
execution/   paper trader, serve loop, LOCKED live stub
portfolio/   quality hurdles, correlation filter, inverse-vol weighting
optimize/    self-optimization (overfitting guard) + million-trade stress test
persistence/ SQLite (WAL) schema + state recovery
dashboard/   Streamlit app
config/      config.yaml + typed Settings + validation + factories
tests/       pytest suite (engine correctness, risk fixes, safety, data, ...)
```

## Quickstart

```bash
pip install -r requirements.txt
python cli.py doctor            # self-test  (--data also tests a real fetch)
python cli.py backtest --strategy supertrend --symbol DOGE/USDT
python cli.py rank --db --limit 40           # evaluate & rank on real data
python cli.py export-active --min-score 55   # write active_combos.yaml
python cli.py serve                          # paper-trade continuously
streamlit run dashboard/app.py               # dashboard
```

On-chain scanning, paper self-trading and the offline advisor:

```bash
python cli.py scan --tradeable-only          # only tokens passing rug filters
python cli.py dex-combos --out active_combos_dex.yaml
python cli.py advise                         # deterministic, offline
python cli.py advise --ollama                # optional: phrase via a FREE local Ollama model
```

Windows users can just run `START.bat`. Further docs:
[`ANLEITUNG.md`](ANLEITUNG.md) (Deutsch), [`SECURITY.md`](SECURITY.md),
[`DEPLOY_GRATIS.md`](DEPLOY_GRATIS.md), [`AUDIT_BERICHT.md`](AUDIT_BERICHT.md),
[`RECHERCHE_MEMECOIN.md`](RECHERCHE_MEMECOIN.md).

## Tests

```bash
pytest -q
```

## License

MIT — see [`LICENSE`](LICENSE). © 2026 Sebastian Renker.

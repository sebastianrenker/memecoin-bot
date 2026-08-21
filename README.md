# Memecoin Paper-Trading Analysis Tool

A **learning and analysis** tool for memecoin trading strategies that trades
**simulated money only**. It fetches **real** market data, backtests strategies
honestly (no look-ahead), validates them (walk-forward + Monte-Carlo + regime),
and paper-trades them continuously with strict risk controls.

> ⚠️ **Not financial advice. No predictions. Simulated money only.**
> Live trading is intentionally **locked** (`execution/live.py` raises
> `LiveTradingNotEnabled`). Memecoins are **extremely** risky: most trend to
> zero, rugpulls are common, liquidity is thin and slippage is high. A positive
> short-term paper result is almost always **noise**, not an edge.

## What it does

- **Real data only** (`data.require_real: true`). CEX-listed memecoins via
  [ccxt](https://github.com/ccxt/ccxt) (real OHLCV) first; an optional on-chain
  DEX adapter (GeckoTerminal) second. If data can't be fetched, the combination
  is **skipped — never faked**.
- **Honest backtest engine**: signal on bar *t* executes at the **open of t+1**
  (no look-ahead); stop checked **before** take-profit; fees + slippage per side;
  leverage capped with the entry fee recomputed on the capped size; too-tight
  stops **rejected** (not widened); bar debounce after exits.
- **Validation**: walk-forward (params fit on train, scored OOS only),
  Monte-Carlo bootstrap (confidence interval + ruin probability), regime
  analysis (ADX/volatility), and a transparent **"works-now" score** (Edge +
  Robustness + Regime + Recency × confidence, with a traffic light and warnings).
- **15 strategies**, indicators implemented from scratch (pandas/numpy):
  `ema_crossover, supertrend, donchian_breakout, dmi_trend, macd_momentum,
  roc_momentum, bollinger_breakout, keltner_pullback, opening_range_breakout,
  rsi_mean_reversion, connors_rsi2, stochastic_reversion, williams_r_reversion,
  cci_reversion, support_resistance`. Mean-reversion is **down-weighted** for
  memecoins by design.
- **Risk management**: 1% risk/trade, max open positions, **daily-loss circuit
  breaker** (safe-hold, auto-resets next UTC day — does *not* kill the process),
  **total-drawdown kill switch** (manual reset), mandatory stops, min stop
  distance, one position per (strategy, symbol).
- **Persistence & operations**: SQLite (WAL) with full **state recovery** on
  restart; a controllable `serve` loop with double-start protection and an
  adjustment thread on its own DB connection.
- **Dashboard**: Streamlit app with paper/risk banners, kill switch, equity
  curve, candle chart with trade markers, ranking, detail, portfolio, heatmap
  and audit log. Read-only cloud mode (`CLOUD_READONLY=1`).
- **Free cloud deploy**: GitHub Actions cron runs `ci-tick` and commits state;
  Streamlit Community Cloud hosts a public read-only view.

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
python cli.py doctor            # self-test
python cli.py doctor --data     # also test a real data fetch
python cli.py backtest --strategy supertrend --symbol DOGE/USDT
python cli.py rank --db --limit 40           # evaluate & rank on real data
python cli.py export-active --min-score 55   # write active_combos.yaml
python cli.py serve                          # paper-trade continuously
streamlit run dashboard/app.py               # dashboard
pytest -q                                    # tests
```

Windows users can just run `START.bat`.

## Honest expectations

This tool quantifies **risk** and describes **past simulated behaviour**. It does
**not** predict the future and there is **no "guaranteed profitable" switch** —
that does not exist. Diversification lowers drawdown; it does not manufacture
winners. Most memecoins go to zero; treat every green light with suspicion.

See [`ANLEITUNG.md`](ANLEITUNG.md) (Deutsch), [`SECURITY.md`](SECURITY.md),
[`DEPLOY_GRATIS.md`](DEPLOY_GRATIS.md), and [`AUDIT_BERICHT.md`](AUDIT_BERICHT.md).

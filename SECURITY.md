# Security & Safety Model

This project is a **paper-trading analysis tool**. Its safety model has two parts:
protecting you from **financial** harm and protecting the software from ordinary
operational mistakes.

## Financial safety (non-negotiable)

- **No live trading.** `execution/live.py` is a locked stub. Every method raises
  `LiveTradingNotEnabled`. There is **no flag, config value, or environment
  variable** that turns this into a real-money trader. `mode: live` is rejected
  by `Settings.validate()`.
- **No real orders, no exchange keys required.** The tool only *reads* public
  market data (ccxt public endpoints, GeckoTerminal/DexScreener public APIs). It
  never needs, asks for, or stores API secrets or private keys. Do **not** add
  exchange API keys — they are not used and would only create risk.
- **Real data only.** `data.require_real: true`. A failed fetch causes the
  combination to be **skipped**, never fabricated.
- **Risk limits are mandatory** and validated: 1% risk/trade, daily-loss circuit
  breaker (3%), total-drawdown kill switch (25%), mandatory stops, minimum stop
  distance, capped leverage. These are floors on prudence, not to be loosened.
- **No profit promises.** Every metric is descriptive of the *simulated* past.
  There are no predictions and no investment advice.

## Operational safety

- **State recovery**: capital and open positions are persisted to SQLite (WAL)
  and restored on restart.
- **Double-start protection**: `serve` refuses to start a second instance while
  a fresh heartbeat + lock file exist.
- **Thread safety**: the serve loop and the adjustment thread use **separate**
  SQLite connections (connections are not shared across threads).
- **Safe-hold breaker**: a tripped daily-loss breaker does not crash the process;
  it holds (no new orders) and auto-resets on a new UTC day.
- **Friendly errors**: the CLI catches exceptions and prints a readable message
  instead of a raw stack trace (set `MEMEBOT_TRACE=1` for a full traceback).

## Data & privacy

- No personal data is collected. No credentials are stored.
- The GitHub Actions workflow commits only the simulated state
  (`cloud/paper.db`, `BOT_STATUS_REPORT.md`, `active_combos.yaml`).

## Reporting

This is a personal learning project. If you find a correctness bug, add a
regression test that fails without the fix (project convention) and fix it.

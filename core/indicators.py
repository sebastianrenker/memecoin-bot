"""Technical indicators, implemented from scratch with pandas/numpy.

No TA-Lib / pandas-ta dependency: every indicator here is transparent and
testable. All functions take a DataFrame with columns
open, high, low, close, volume and return pandas Series/DataFrame aligned to it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder's ATR (RMA smoothing)."""
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss == 0 => RSI 100; when avg_gain == 0 => RSI 0.
    out = out.where(avg_loss != 0.0, 100.0)
    out = out.where(avg_gain != 0.0, out.where(avg_loss == 0.0, 0.0))
    return out


def roc(s: pd.Series, n: int = 12) -> pd.Series:
    return (s / s.shift(n) - 1.0) * 100.0


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(s, fast) - ema(s, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(s, n)
    sd = s.rolling(n, min_periods=n).std(ddof=0)
    upper = mid + k * sd
    lower = mid - k * sd
    return lower, mid, upper


def keltner(df: pd.DataFrame, n: int = 20, mult: float = 2.0):
    mid = ema(df["close"], n)
    rng = atr(df, n)
    upper = mid + mult * rng
    lower = mid - mult * rng
    return lower, mid, upper


def donchian(df: pd.DataFrame, n: int = 20):
    upper = df["high"].rolling(n, min_periods=n).max()
    lower = df["low"].rolling(n, min_periods=n).min()
    mid = (upper + lower) / 2.0
    return lower, mid, upper


def supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0):
    """Return (supertrend_line, direction) where direction is +1 uptrend / -1 down."""
    hl2 = (df["high"] + df["low"]) / 2.0
    rng = atr(df, period)
    upperband = hl2 + mult * rng
    lowerband = hl2 - mult * rng

    close = df["close"].values
    ub = upperband.values.copy()
    lb = lowerband.values.copy()
    st = np.full(len(df), np.nan)
    dirn = np.zeros(len(df), dtype=int)

    for i in range(len(df)):
        if i == 0 or np.isnan(ub[i]) or np.isnan(lb[i]):
            st[i] = ub[i] if not np.isnan(ub[i]) else np.nan
            dirn[i] = -1
            continue
        # Tighten bands.
        if not np.isnan(ub[i - 1]):
            if close[i - 1] <= ub[i - 1]:
                ub[i] = min(ub[i], ub[i - 1])
            if close[i - 1] >= lb[i - 1]:
                lb[i] = max(lb[i], lb[i - 1])
        prev_dir = dirn[i - 1] if dirn[i - 1] != 0 else -1
        if prev_dir == -1:
            dirn[i] = 1 if close[i] > ub[i - 1] else -1
        else:
            dirn[i] = -1 if close[i] < lb[i - 1] else 1
        st[i] = lb[i] if dirn[i] == 1 else ub[i]

    return pd.Series(st, index=df.index), pd.Series(dirn, index=df.index)


def dmi_adx(df: pd.DataFrame, n: int = 14):
    """Return (plus_di, minus_di, adx) using Wilder smoothing."""
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    tr = true_range(df)
    atr_n = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    plus_di = 100.0 * (plus_dm.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr_n)
    minus_di = 100.0 * (minus_dm.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr_n)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx = dx.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    return plus_di, minus_di, adx


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3):
    low_n = df["low"].rolling(k, min_periods=k).min()
    high_n = df["high"].rolling(k, min_periods=k).max()
    percent_k = 100.0 * (df["close"] - low_n) / (high_n - low_n).replace(0.0, np.nan)
    percent_d = percent_k.rolling(d, min_periods=d).mean()
    return percent_k, percent_d


def williams_r(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high_n = df["high"].rolling(n, min_periods=n).max()
    low_n = df["low"].rolling(n, min_periods=n).min()
    return -100.0 * (high_n - df["close"]) / (high_n - low_n).replace(0.0, np.nan)


def cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    ma = tp.rolling(n, min_periods=n).mean()
    md = (tp - ma).abs().rolling(n, min_periods=n).mean()
    return (tp - ma) / (0.015 * md.replace(0.0, np.nan))


def connors_rsi(df: pd.DataFrame, rsi_n: int = 3, streak_n: int = 2, rank_n: int = 100):
    """ConnorsRSI = avg(RSI(close, rsi_n), RSI(streak, streak_n), PercentRank(ROC1, rank_n))."""
    close = df["close"]
    price_rsi = rsi(close, rsi_n)

    # Up/down streak length (signed).
    change = close.diff()
    streak = np.zeros(len(close))
    for i in range(1, len(close)):
        if change.iloc[i] > 0:
            streak[i] = streak[i - 1] + 1 if streak[i - 1] > 0 else 1
        elif change.iloc[i] < 0:
            streak[i] = streak[i - 1] - 1 if streak[i - 1] < 0 else -1
        else:
            streak[i] = 0
    streak = pd.Series(streak, index=close.index)
    streak_rsi = rsi(streak, streak_n)

    roc1 = close.pct_change() * 100.0

    def _pct_rank(x: pd.Series) -> float:
        if x.isna().any() or len(x) < 2:
            return np.nan
        last = x.iloc[-1]
        prior = x.iloc[:-1]
        return 100.0 * (prior < last).sum() / len(prior)

    pct_rank = roc1.rolling(rank_n + 1, min_periods=rank_n + 1).apply(_pct_rank, raw=False)
    return (price_rsi + streak_rsi + pct_rank) / 3.0

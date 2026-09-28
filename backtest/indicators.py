"""Vectorized indicators for research (pandas/numpy). Every value at bar t uses bars <= t only."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def wilder(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up, dn = wilder(d.clip(lower=0), n), wilder(-d.clip(upper=0), n)
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).where(dn != 0, 100.0)


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df.close.shift(1)
    return pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return wilder(true_range(df), n)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return mid - k * sd, mid, mid + k * sd


def donchian_high(df: pd.DataFrame, n: int) -> pd.Series:
    """Highest high of the PREVIOUS n bars (excludes the current bar)."""
    return df.high.rolling(n, min_periods=n).max().shift(1)


def donchian_low(df: pd.DataFrame, n: int) -> pd.Series:
    return df.low.rolling(n, min_periods=n).min().shift(1)


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df.high.diff()
    dn = -df.low.diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = wilder(true_range(df), n)
    pdi, mdi = 100 * wilder(plus, n) / tr, 100 * wilder(minus, n) / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return wilder(dx.fillna(0), n)


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP reset at 00:00 UTC each day, using typical price; value at bar t includes bar t."""
    tp = (df.high + df.low + df.close) / 3
    day = df.index.floor("1D")
    pv = (tp * df.volume).groupby(day).cumsum()
    v = df.volume.groupby(day).cumsum()
    return (pv / v.replace(0, np.nan)).ffill()


def rolling_percentile_rank(s: pd.Series, window: int) -> pd.Series:
    """Percentile (0-100) of the current value within the trailing window (inclusive)."""
    return s.rolling(window, min_periods=window).rank(pct=True) * 100

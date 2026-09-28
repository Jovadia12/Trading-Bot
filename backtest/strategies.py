"""Pre-registered long-only strategy families and their parameter grids.

Written BEFORE any price data was available in this repository (see STRATEGY_RESEARCH_PROTOCOL.md),
so the grids cannot have been tuned to the data. Each grid is small and uses conventional values.
Every family has a protective stop (needed for risk-based position sizing).
Indicators use closed bars only; entries/exits execute per backtest/engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable

import numpy as np
import pandas as pd

from backtest.engine import Signals
from backtest import indicators as ind


def _ok(*arrays) -> np.ndarray:
    m = np.ones(len(arrays[0]), bool)
    for a in arrays:
        m &= np.isfinite(np.asarray(a, float))
    return m


def _nan(n):
    return np.full(n, np.nan)


# 1. Bollinger Band mean reversion ------------------------------------------------------------------
def bb_reversion(df, k=2.0, stop_atr=2.0, n=20):
    lo, mid, _ = ind.bollinger(df.close, n, k)
    a = ind.atr(df)
    entry = (df.close < lo).to_numpy() & _ok(lo, a)
    return Signals(entry, (stop_atr * a).to_numpy(), None, (df.close >= mid).to_numpy(), max_hold=3 * n)


# 2. Bollinger + RSI + EMA trend filter -------------------------------------------------------------
def bb_rsi_ema(df, k=2.0, rsi_max=30, ema_n=200, stop_atr=2.0, n=20):
    lo, mid, _ = ind.bollinger(df.close, n, k)
    r, e, a = ind.rsi(df.close, 14), ind.ema(df.close, ema_n), ind.atr(df)
    entry = ((df.close < lo) & (r < rsi_max) & (df.close > e)).to_numpy() & _ok(lo, r, a) & (np.arange(len(df)) >= ema_n)
    return Signals(entry, (stop_atr * a).to_numpy(), None, (df.close >= mid).to_numpy(), max_hold=3 * n)


# 3. EMA pullback in an uptrend ---------------------------------------------------------------------
def ema_pullback(df, stop_atr=1.5, tp_r=2.0, fast=20, mid=50, slow=200):
    ef, em, es, a = ind.ema(df.close, fast), ind.ema(df.close, mid), ind.ema(df.close, slow), ind.atr(df)
    trend = (em > es) & (df.close > es)
    touch = (df.low <= ef) & (df.close > ef) & (df.close.shift(1) > ef.shift(1))
    entry = (trend & touch).to_numpy() & _ok(a) & (np.arange(len(df)) >= slow)
    sd = (stop_atr * a).to_numpy()
    return Signals(entry, sd, tp_r * sd, None, max_hold=100)


# 4. RSI mean reversion -----------------------------------------------------------------------------
def rsi_reversion(df, setting=(2, 10), stop_atr=2.5, trend_n=200):
    rsi_n, threshold = setting
    r, e, a, s5 = ind.rsi(df.close, rsi_n), ind.ema(df.close, trend_n), ind.atr(df), ind.sma(df.close, 5)
    entry = ((r < threshold) & (df.close > e)).to_numpy() & _ok(r, a, s5) & (np.arange(len(df)) >= trend_n)
    return Signals(entry, (stop_atr * a).to_numpy(), None, (df.close > s5).to_numpy(), max_hold=20)


# 5. VWAP reversion (session VWAP, UTC day) ---------------------------------------------------------
def vwap_reversion(df, k=1.5, trend=True, stop_atr=2.0, trend_n=200):
    v, a, e = ind.session_vwap(df), ind.atr(df), ind.ema(df.close, trend_n)
    cond = df.close < v - k * a
    if trend:
        cond &= df.close > e
    entry = cond.to_numpy() & _ok(v, a) & (np.arange(len(df)) >= (trend_n if trend else 14))
    return Signals(entry, (stop_atr * a).to_numpy(), None, (df.close >= v).to_numpy(), max_hold=96)


# 6. Momentum / trend following: EMA cross ----------------------------------------------------------
def ema_cross(df, pair=(20, 60), stop_atr=3.0):
    fast, slow = pair
    f, s, a = ind.ema(df.close, fast), ind.ema(df.close, slow), ind.atr(df)
    up = (f > s) & (f.shift(1) <= s.shift(1))
    entry = up.to_numpy() & _ok(a) & (np.arange(len(df)) >= slow)
    return Signals(entry, (stop_atr * a).to_numpy(), None, (f < s).to_numpy())


# 7. Breakout + ATR (Donchian) -----------------------------------------------------------------------
def donchian_breakout(df, n=20, stop_atr=2.0):
    hi, lo, a = ind.donchian_high(df, n), ind.donchian_low(df, max(2, n // 2)), ind.atr(df)
    entry = (df.close > hi).to_numpy() & _ok(hi, a)
    return Signals(entry, (stop_atr * a).to_numpy(), None, (df.close < lo).to_numpy())


# 8. Volatility regime: squeeze breakout -------------------------------------------------------------
def squeeze_breakout(df, pct=20, tp_r=2.0, stop_atr=2.0, n=20, lookback=500):
    lo, mid, up = ind.bollinger(df.close, n, 2.0)
    width = (up - lo) / mid
    rank = ind.rolling_percentile_rank(width, lookback).shift(1)   # squeeze measured on the previous bar
    a = ind.atr(df)
    entry = ((rank < pct) & (df.close > up)).to_numpy() & _ok(rank, a)
    sd = (stop_atr * a).to_numpy()
    return Signals(entry, sd, tp_r * sd, None, max_hold=5 * n)


# 9. Market-regime switching: ADX trend vs range -----------------------------------------------------
def regime_switch(df, adx_level=25, stop_atr=2.0, n=20):
    x, a = ind.adx(df), ind.atr(df)
    lo, mid, _ = ind.bollinger(df.close, n, 2.0)
    hi = ind.donchian_high(df, n)
    trending, ranging = x >= adx_level, x < adx_level
    trend_entry = trending & (df.close > hi)
    range_entry = ranging & (df.close < lo)
    entry = (trend_entry | range_entry).to_numpy() & _ok(x, a, lo, hi)
    dl = ind.donchian_low(df, max(2, n // 2))
    # exits follow the mode active at the exit bar: trend -> close < N/2-low; range -> close >= middle band
    exit_sig = ((trending & (df.close < dl)) | (ranging & (df.close >= mid))).to_numpy()
    return Signals(entry, (stop_atr * a).to_numpy(), None, exit_sig, max_hold=10 * n)


# 10. Hybrid: trend filter + mean-reversion entry + trend-following (chandelier) exit ----------------
def hybrid_trend_mr(df, rsi_max=35, trail_atr=3.0, ema_n=200, stop_atr=2.0):
    r, e, a = ind.rsi(df.close, 14), ind.ema(df.close, ema_n), ind.atr(df)
    rising = e > e.shift(10)
    entry = ((r < rsi_max) & (df.close > e) & rising).to_numpy() & _ok(r, a) & (np.arange(len(df)) >= ema_n)
    return Signals(entry, (stop_atr * a).to_numpy(), None, None, trail_dist=(trail_atr * a).to_numpy())


@dataclass(frozen=True)
class Family:
    key: str
    name: str
    fn: Callable
    grid: dict            # parameter -> ordered list of values (ordered so "neighbours" are meaningful)

    def combos(self) -> list[dict]:
        keys = list(self.grid)
        return [dict(zip(keys, vals)) for vals in product(*(self.grid[k] for k in keys))]


FAMILIES: list[Family] = [
    Family("bb_mr", "Bollinger Band mean reversion", bb_reversion,
           {"k": [1.5, 2.0, 2.5], "stop_atr": [2.0, 3.0]}),
    Family("bb_rsi_ema", "Bollinger + RSI + EMA trend filter", bb_rsi_ema,
           {"k": [1.5, 2.0, 2.5], "rsi_max": [30, 40], "ema_n": [100, 200]}),
    Family("ema_pullback", "EMA pullback (20 EMA in 50>200 uptrend)", ema_pullback,
           {"stop_atr": [1.5, 2.0], "tp_r": [1.5, 2.0, 3.0]}),
    Family("rsi_mr", "RSI mean reversion (above EMA200)", rsi_reversion,
           {"setting": [(2, 5), (2, 10), (2, 15), (14, 25), (14, 30)]}),
    Family("vwap_mr", "Session-VWAP reversion", vwap_reversion,
           {"k": [1.0, 1.5, 2.0], "trend": [True, False]}),
    Family("ema_cross", "Momentum: EMA crossover", ema_cross,
           {"pair": [(10, 30), (20, 60), (50, 150)], "stop_atr": [2.0, 3.0]}),
    Family("donchian", "Breakout + ATR (Donchian)", donchian_breakout,
           {"n": [20, 50, 100], "stop_atr": [1.5, 2.5]}),
    Family("squeeze", "Volatility regime: BB squeeze breakout", squeeze_breakout,
           {"pct": [10, 20, 30], "tp_r": [2.0, 3.0]}),
    Family("regime_switch", "Regime switching: ADX trend/range", regime_switch,
           {"adx_level": [20, 25, 30], "stop_atr": [2.0, 3.0]}),
    Family("hybrid", "Hybrid: trend filter + MR entry + chandelier exit", hybrid_trend_mr,
           {"rsi_max": [30, 40], "trail_atr": [2.0, 3.0], "ema_n": [100, 200]}),
]
def build(family: Family, df: pd.DataFrame, params: dict) -> Signals:
    return family.fn(df, **params)


def grid_size() -> int:
    return sum(len(f.combos()) for f in FAMILIES)

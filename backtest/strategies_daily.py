"""Pre-registered DAILY / 2-day / 3-day long-only families (study "daily"; see DAILY_STRATEGY_PROTOCOL.md).

Fixed BEFORE this study was run. Long only, spot, no leverage; every family has an ATR(14) protective
stop. All lookbacks are in BARS of the tested timeframe (so on 3d bars EMA200 spans ~600 days).
Indicators use closed bars only. Entries are "state became true" transitions unless noted, so a
position that is stopped out is not re-entered on the very next bar while nothing has changed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import indicators as ind
from backtest.engine import Signals
from backtest.strategies import Family, _ok


def _became_true(state: pd.Series) -> np.ndarray:
    s = state.fillna(False).astype(bool)
    return (s & ~s.shift(1, fill_value=False)).to_numpy()


def ema_trend(df, pair=(20, 50), stop_atr=2.0, exit_rule="cross"):
    """1. Daily trend following. State: EMA(fast) > EMA(slow) and close > EMA(fast); enter when it turns on.
    Exit at the next open when exit_rule='cross': EMA(fast) < EMA(slow); 'price': close < EMA(fast)."""
    f, s = pair
    ef, es, a = ind.ema(df.close, f), ind.ema(df.close, s), ind.atr(df)
    entry = _became_true((ef > es) & (df.close > ef)) & _ok(a) & (np.arange(len(df)) >= s)
    ex = (ef < es) if exit_rule == "cross" else (df.close < ef)
    return Signals(entry, (stop_atr * a).to_numpy(), None, ex.to_numpy())


def breakout(df, n=20, stop_atr=2.0, trend_filter="none"):
    """2. Donchian breakout: close > previous-N-bar high (optionally close > SMA200).
    Stop stop_atr x ATR; exit when close < previous-(N//2)-bar low, at the next open."""
    hi, lo, a = ind.donchian_high(df, n), ind.donchian_low(df, max(2, n // 2)), ind.atr(df)
    cond = df.close > hi
    warm = n
    if trend_filter == "sma200":
        cond &= df.close > ind.sma(df.close, 200)
        warm = 200
    entry = cond.to_numpy() & _ok(hi, a) & (np.arange(len(df)) >= warm)
    return Signals(entry, (stop_atr * a).to_numpy(), None, (df.close < lo).to_numpy())


def pullback(df, pb_ema=20, stop_atr=2.0, trail_atr=3.0, lookback=5, confirm_n=3):
    """3. Pullback / continuation in a strong trend.
    Strong trend: close > EMA200, EMA50 > EMA200 and EMA50 higher than 10 bars ago. Pullback: some bar in the
    last `lookback` had low <= EMA(pb_ema). Continuation: close > previous-`confirm_n`-bar high.
    Stop stop_atr x ATR; exit only by a chandelier trail close - trail_atr x ATR (ratchets up)."""
    e50, e200, ep, a = ind.ema(df.close, 50), ind.ema(df.close, 200), ind.ema(df.close, pb_ema), ind.atr(df)
    strong = (df.close > e200) & (e50 > e200) & (e50 > e50.shift(10))
    touched = (df.low <= ep).astype(float).rolling(lookback, min_periods=lookback).max() > 0
    cont = df.close > ind.donchian_high(df, confirm_n)
    entry = (strong & touched & cont).to_numpy() & _ok(a) & (np.arange(len(df)) >= 200)
    return Signals(entry, (stop_atr * a).to_numpy(), None, None, trail_dist=(trail_atr * a).to_numpy())


def regime_trend(df, sma_n=200, vol_pct=100, stop_atr=3.0, rank_window=250):
    """4. Long-term trend + volatility regime filter.
    State: close > SMA(sma_n) and ATR%(14) percentile rank over `rank_window` bars <= vol_pct (100 = no vol
    filter). Enter when the state turns on; exit at the next open when close < SMA(sma_n)."""
    m, a = ind.sma(df.close, sma_n), ind.atr(df)
    state = df.close > m
    warm = sma_n
    if vol_pct < 100:
        rank = ind.rolling_percentile_rank(a / df.close, rank_window)
        state &= rank <= vol_pct
        warm = max(sma_n, rank_window)
    entry = _became_true(state) & _ok(m, a) & (np.arange(len(df)) >= warm)
    return Signals(entry, (stop_atr * a).to_numpy(), None, (df.close < m).to_numpy())


def hybrid(df, n=20, stop_atr=2.0, trail_atr=3.0):
    """5. Trend + (breakout OR pullback-continuation). Trend: close > EMA200 and EMA50 > EMA200.
    Entry: close > previous-N-bar high, OR (a low <= EMA20 in the last 5 bars and close > previous-3-bar high).
    Stop stop_atr x ATR; exit only by a chandelier trail close - trail_atr x ATR."""
    e20, e50, e200, a = ind.ema(df.close, 20), ind.ema(df.close, 50), ind.ema(df.close, 200), ind.atr(df)
    trend = (df.close > e200) & (e50 > e200)
    brk = df.close > ind.donchian_high(df, n)
    pb = ((df.low <= e20).astype(float).rolling(5, min_periods=5).max() > 0) & (df.close > ind.donchian_high(df, 3))
    entry = (trend & (brk | pb)).to_numpy() & _ok(a) & (np.arange(len(df)) >= 200)
    return Signals(entry, (stop_atr * a).to_numpy(), None, None, trail_dist=(trail_atr * a).to_numpy())


DAILY_FAMILIES: list[Family] = [
    Family("ema_trend", "Daily EMA trend following", ema_trend,
           {"pair": [(20, 50), (50, 200)], "stop_atr": [2.0, 3.0], "exit_rule": ["cross", "price"]}),
    Family("breakout", "Donchian breakout + ATR stop", breakout,
           {"n": [10, 20, 30, 50], "stop_atr": [2.0, 3.0], "trend_filter": ["none", "sma200"]}),
    Family("pullback", "Strong-trend pullback / continuation, chandelier exit", pullback,
           {"pb_ema": [20, 50], "stop_atr": [2.0, 3.0], "trail_atr": [3.0, 5.0]}),
    Family("regime_trend", "Long-term trend + volatility regime filter", regime_trend,
           {"sma_n": [100, 200], "vol_pct": [50, 80, 100], "stop_atr": [3.0, 5.0]}),
    Family("hybrid", "Trend + breakout/pullback, chandelier exit", hybrid,
           {"n": [20, 30], "stop_atr": [2.0, 3.0], "trail_atr": [3.0, 5.0]}),
]
DAILY_TIMEFRAMES = ["1d", "2d", "3d"]

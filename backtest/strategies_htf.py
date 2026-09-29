"""Pre-registered 2H/4H/6H trend/momentum families (study "htf"; see HTF_STRATEGY_PROTOCOL.md).

Fixed BEFORE running this study. Long only; every family has an ATR(14) protective stop.
Indicators use closed bars only; execution per backtest/engine.py (next-open taker entries,
stop-market stops with gap fills, stop-first on ambiguous bars, trailing stops from the close).
"""
from __future__ import annotations

import numpy as np

from backtest import indicators as ind
from backtest.engine import Signals
from backtest.strategies import Family, _ok


def breakout_trail(df, n=20, ema_slow=200, stop_atr=2.0, trail_atr=3.0):
    """1. Higher-timeframe breakout: close > previous-N-bar high and close > EMA(slow).
    Stop stop_atr x ATR; exit ONLY by a chandelier trail (close - trail_atr x ATR, ratchets up)."""
    hi, es, a = ind.donchian_high(df, n), ind.ema(df.close, ema_slow), ind.atr(df)
    entry = ((df.close > hi) & (df.close > es)).to_numpy() & _ok(hi, a) & (np.arange(len(df)) >= ema_slow)
    return Signals(entry, (stop_atr * a).to_numpy(), None, None, trail_dist=(trail_atr * a).to_numpy())


def pullback_continuation(df, ema_fast=20, ema_slow=200, stop_atr=2.0, pullback_bars=5, confirm_n=5):
    """2. EMA pullback + breakout continuation.
    Trend: EMA(fast) > EMA(slow) and close > EMA(slow). Pullback: some bar in the last `pullback_bars`
    (including this one) had low <= EMA(fast). Confirmation: close > previous-`confirm_n`-bar high.
    Stop stop_atr x ATR; exit when close < EMA(fast) (trend deterioration), at the next open."""
    ef, es, a = ind.ema(df.close, ema_fast), ind.ema(df.close, ema_slow), ind.atr(df)
    touched = (df.low <= ef).astype(float).rolling(pullback_bars, min_periods=pullback_bars).max() > 0
    confirm = df.close > ind.donchian_high(df, confirm_n)
    trend = (ef > es) & (df.close > es)
    entry = (trend & touched & confirm).to_numpy() & _ok(a) & (np.arange(len(df)) >= ema_slow)
    return Signals(entry, (stop_atr * a).to_numpy(), None, (df.close < ef).to_numpy())


def donchian_trend(df, n=20, stop_atr=2.0):
    """3. Donchian breakout + EMA trend filter: close > previous-N-bar high and EMA50 > EMA200.
    Stop stop_atr x ATR; exit when close < previous-(N//2)-bar low, at the next open."""
    hi, lo = ind.donchian_high(df, n), ind.donchian_low(df, max(2, n // 2))
    e50, e200, a = ind.ema(df.close, 50), ind.ema(df.close, 200), ind.atr(df)
    entry = ((df.close > hi) & (e50 > e200)).to_numpy() & _ok(hi, a) & (np.arange(len(df)) >= 200)
    return Signals(entry, (stop_atr * a).to_numpy(), None, (df.close < lo).to_numpy())


HTF_FAMILIES: list[Family] = [
    Family("htf_breakout", "HTF breakout + EMA filter, chandelier trail", breakout_trail,
           {"n": [10, 20, 30], "ema_slow": [100, 200], "stop_atr": [1.5, 2.5]}),
    Family("ema_pullback_cont", "EMA pullback + breakout continuation", pullback_continuation,
           {"ema_fast": [20, 50], "ema_slow": [100, 200], "stop_atr": [1.5, 2.5]}),
    Family("donchian_ema", "Donchian breakout + EMA50>EMA200", donchian_trend,
           {"n": [10, 15, 20, 30], "stop_atr": [1.5, 2.0, 2.5]}),
]
HTF_TIMEFRAMES = ["2h", "4h", "6h"]

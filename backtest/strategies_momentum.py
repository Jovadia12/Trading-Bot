"""Pre-registered BTC Momentum Breakout versions (study "momentum"; see MOMENTUM_BREAKOUT_PROTOCOL.md).

Fixed BEFORE the study was run on real data. Long only. Every value at bar t uses completed bars <= t;
the Donchian high and the volume SMA exclude the current bar (they describe the PREVIOUS N bars).
Exits are described by an ExitSpec and executed by backtest/momentum_engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable, Optional

import numpy as np
import pandas as pd

from backtest import indicators as ind


@dataclass(frozen=True)
class ExitSpec:
    stop_atr: float                          # initial stop = entry - stop_atr * ATR(signal bar)  (1R)
    trail_atr: float                         # trail = highest close since entry - trail_atr * ATR(current bar)
    trail_from_entry: bool                   # True: trail active from entry; False: only after the partial exit
    partial_r: Optional[float] = None        # take `partial_frac` off at entry + partial_r * R (None = no partial)
    partial_frac: float = 0.5
    breakeven_after_partial: bool = False    # remaining stop -> entry price after the partial exit
    time_exit_hours: Optional[float] = None  # exit if, after this long, the high has never exceeded +time_exit_r R
    time_exit_r: float = 0.5


@dataclass
class MomentumSignals:
    entry: np.ndarray        # bool, signal at the close of bar i -> entry on bar i+1
    atr: np.ndarray          # ATR(14) at each bar close
    exit: ExitSpec
    bar_hours: float


def _trend_breakout(df: pd.DataFrame, n: int):
    e50, e200 = ind.ema(df.close, 50), ind.ema(df.close, 200)
    hi = ind.donchian_high(df, n)
    a = ind.atr(df)
    cond = (e50 > e200) & (df.close > e50) & (df.close > hi)
    ok = np.isfinite(hi.to_numpy()) & np.isfinite(a.to_numpy()) & (np.arange(len(df)) >= 200)
    return cond.to_numpy() & ok, a


def conservative(df, n=20, stop_atr=1.5, trail_atr=2.0, bar_hours=4.0):
    """A) EMA50 > EMA200, close > EMA50, close > previous-N-bar high. Stop stop_atr x ATR; exit only by the
    2-ATR trail from the highest close since entry (active from entry, never lowers the stop)."""
    entry, a = _trend_breakout(df, n)
    return MomentumSignals(entry, a.to_numpy(), ExitSpec(stop_atr, trail_atr, True), bar_hours)


def filtered(df, n=20, stop_atr=1.5, vol_mult=1.2, rsi_lo=55.0, rsi_hi=75.0, atr_lo=0.004, atr_hi=0.03,
             partial_r=2.0, trail_atr=2.0, time_exit_hours=24.0, time_exit_r=0.5, bar_hours=1.0):
    """B/C) Trend + breakout + volume > vol_mult x SMA20(volume of the previous 20 bars) + RSI14 in
    [rsi_lo, rsi_hi] + ATR14/close in [atr_lo, atr_hi]. Exit: stop 1R = stop_atr x ATR; 50% off at +partial_r R;
    then remaining stop -> breakeven and trail = highest close since entry - trail_atr x ATR; time exit if the
    high has not exceeded +time_exit_r R after time_exit_hours."""
    entry, a = _trend_breakout(df, n)
    vsma = df.volume.rolling(20, min_periods=20).mean().shift(1)
    r = ind.rsi(df.close, 14)
    atr_pct = a / df.close
    filt = (df.volume > vol_mult * vsma) & (r >= rsi_lo) & (r <= rsi_hi) & (atr_pct >= atr_lo) & (atr_pct <= atr_hi)
    entry = entry & filt.to_numpy() & np.isfinite(vsma.to_numpy())
    spec = ExitSpec(stop_atr, trail_atr, False, partial_r, 0.5, True, time_exit_hours, time_exit_r)
    return MomentumSignals(entry, a.to_numpy(), spec, bar_hours)


@dataclass(frozen=True)
class Version:
    key: str
    name: str
    tf: str
    fn: Callable
    base: dict                    # fixed arguments
    grid: dict                    # selection grid (train only); {} = a single pre-specified configuration
    perturb: dict                 # one-at-a-time robustness perturbations (NOT used for selection)
    min_train_trades: int
    min_val_trades: int
    min_oos_trades: int
    min_wf_trades: int
    wf_min_train_trades: int

    def combos(self) -> list[dict]:
        if not self.grid:
            return [{}]
        keys = list(self.grid)
        return [dict(zip(keys, v)) for v in product(*(self.grid[k] for k in keys))]

    def params(self, combo: dict) -> dict:
        return {**self.base, **combo}

    def neighbours(self, combo: dict) -> list[dict]:
        """Grid neighbours (one step) + one-at-a-time perturbations of the non-grid parameters."""
        full = self.params(combo)
        out = []
        for k, vals in self.grid.items():
            i = vals.index(combo[k])
            out += [{**combo, k: vals[j]} for j in (i - 1, i + 1) if 0 <= j < len(vals)]
        for k, vals in self.perturb.items():
            out += [{**combo, k: v} for v in vals if v != full.get(k)]
        return out

    def build(self, df, combo: dict) -> MomentumSignals:
        return self.fn(df, **self.params(combo))


VERSIONS: list[Version] = [
    Version("A_4h_conservative", "4H Conservative", "4h", conservative, {"trail_atr": 2.0, "bar_hours": 4.0},
            {"n": [20, 30], "stop_atr": [1.5, 2.0]}, {"trail_atr": [1.5, 2.5]},
            min_train_trades=40, min_val_trades=8, min_oos_trades=15, min_wf_trades=40, wf_min_train_trades=12),
    Version("B_1h_main", "1H Main", "1h", filtered,
            {"n": 20, "stop_atr": 1.5, "vol_mult": 1.2, "rsi_lo": 55.0, "rsi_hi": 75.0, "atr_lo": 0.004, "atr_hi": 0.03,
             "partial_r": 2.0, "trail_atr": 2.0, "time_exit_hours": 24.0, "time_exit_r": 0.5, "bar_hours": 1.0},
            {}, {"n": [15, 25], "stop_atr": [1.25, 1.75], "vol_mult": [1.0, 1.5], "partial_r": [1.5, 2.5],
                 "trail_atr": [1.5, 2.5], "time_exit_hours": [12.0, 48.0]},
            min_train_trades=0, min_val_trades=20, min_oos_trades=30, min_wf_trades=80, wf_min_train_trades=0),
    Version("C_15m_faster", "15M Faster", "15m", filtered,
            {"vol_mult": 1.2, "rsi_lo": 55.0, "rsi_hi": 75.0, "atr_lo": 0.002, "atr_hi": 0.015,
             "partial_r": 2.0, "trail_atr": 2.0, "time_exit_hours": 24.0, "time_exit_r": 0.5, "bar_hours": 0.25},
            {"n": [20, 40], "stop_atr": [1.5, 2.0]}, {"vol_mult": [1.0, 1.5], "trail_atr": [1.5, 2.5]},
            min_train_trades=150, min_val_trades=30, min_oos_trades=50, min_wf_trades=150, wf_min_train_trades=40),
]

"""Version A (paper trading): 4H Donchian-style breakout, long-only, 1.5 ATR protective stop.

Specification (as given for this implementation; the original research code defining
Version A -- spotlab/lab.py -- is not in this repository, see RESEARCH_AUDIT.md §4.6):
  * Evaluate only when a 4H candle CLOSES.
  * Entry: that candle's close > highest high of the PREVIOUS 20 completed 4H candles.
  * Stop: entry fill price - 1.5 x ATR, ATR = Wilder ATR(14) on 4H candles as of the signal candle.
  * Sizing: risk 0.5% of current paper equity over the stop distance; entered in full at once.
  * Exit: the stop only. No filters, RSI, breakeven, partial exits, time exits, leverage or shorts.
The stop is FIXED at entry (not trailed) because no trailing rule was specified.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Iterable, Optional, Sequence

from market_data.models import Candle
from strategy.base import Signal
from strategy.indicators import atr_wilder, highest_high


@dataclass(frozen=True)
class VersionAParams:
    lookback: int = 20
    atr_period: int = 14
    stop_atr_mult: Decimal = Decimal("1.5")
    risk_fraction: Decimal = Decimal("0.005")

    @property
    def min_history(self) -> int:
        """Completed candles needed BEFORE the first evaluated candle."""
        return max(self.lookback, self.atr_period)


def breakout(previous: Sequence[Candle], candle: Candle, lookback: int = 20) -> Optional[Decimal]:
    """Return the breakout level if candle.close > highest high of the previous `lookback` candles."""
    if len(previous) < lookback:
        return None
    level = highest_high(previous[-lookback:])
    return level if candle.close > level else None


class VersionA:
    name = "version_a"

    def __init__(self, params: VersionAParams = VersionAParams(), max_history: int = 500):
        self.params = params
        self.history: deque[Candle] = deque(maxlen=max_history)

    @property
    def ready(self) -> bool:
        return len(self.history) >= self.params.min_history

    def warm_up(self, candles: Iterable[Candle]) -> int:
        for c in candles:
            self._append(c)
        return len(self.history)

    def _append(self, candle: Candle) -> None:
        if self.history and candle.start <= self.history[-1].start:
            raise ValueError("candles must be appended in strictly increasing time order")
        self.history.append(candle)

    def on_candle_close(self, candle: Candle) -> Optional[Signal]:
        """Feed EVERY closed 4H candle (also while in a position). Returns ENTER_LONG on a breakout."""
        previous = list(self.history)
        self._append(candle)
        if len(previous) < self.params.min_history:
            return None
        level = breakout(previous, candle, self.params.lookback)
        if level is None:
            return None
        atr = atr_wilder(list(self.history), self.params.atr_period)
        if atr <= 0:
            return None
        p = self.params
        return Signal(
            time=candle.start, action="ENTER_LONG",
            label=f"VersionA: 4H close {candle.close} > {p.lookback}-candle high {level}; "
                  f"stop {p.stop_atr_mult} x ATR{p.atr_period} ({atr:.2f})",
            stop_distance=p.stop_atr_mult * atr, atr=atr, reference_price=level, candle_close=candle.close)


@dataclass(frozen=True)
class SizeDecision:
    base: Decimal
    risk_based_base: Decimal
    cash_capped: bool
    risk_usd: Decimal


def size_position(equity: Decimal, stop_distance: Decimal, price: Decimal, available_usd: Decimal,
                  taker_fee_rate: Decimal, base_increment: Decimal,
                  risk_fraction: Decimal = Decimal("0.005"), cash_buffer: Decimal = Decimal("0.002")) -> SizeDecision:
    """Risk `risk_fraction` of equity over `stop_distance`; never spend more USD than available.

    base = equity * risk / stop_distance, capped so that base * price * (1 + fee) * (1 + buffer)
    <= available USD (the buffer covers spread/slippage between sizing and fill). Rounded DOWN to
    the product's base increment.
    """
    if stop_distance <= 0 or price <= 0:
        raise ValueError("stop distance and price must be positive")
    risk_usd = equity * risk_fraction
    risk_base = risk_usd / stop_distance
    cash_base = max(Decimal(0), available_usd) / (price * (1 + taker_fee_rate) * (1 + cash_buffer))
    base = min(risk_base, cash_base)
    base = (base / base_increment).to_integral_value(rounding=ROUND_DOWN) * base_increment
    return SizeDecision(base=base, risk_based_base=risk_base, cash_capped=cash_base < risk_base, risk_usd=risk_usd)

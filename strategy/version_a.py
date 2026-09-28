"""Version A (paper trading), per the original backtester definition as provided by the user.

Source (reported by the user from btc_backtester.zip; the file itself is NOT in this repository):
run_higher_tf.py  BASE = Flags(trend_filter=True, ema20_entry=False, rsi_filter=False, ext_filter=False,
                               partials=False, breakeven=False, ema20_exit=True, trail_exit=False,
                               risk_controls=True)
config.py StrategyParams: atr_len=14, stop_atr_mult=1.5, risk_per_trade=0.10 (paper default overridden
to 0.15 on request), ema_1h=20, trail_lookback=10 (unused: trail_exit=False).

Rules implemented (4H candles, evaluated only at candle close, long-only, one position at a time):
  * Trend filter: close > EMA200 and EMA50 > EMA200 (4H closes).
  * Entry signal: close > highest high of the PREVIOUS 20 completed 4H candles.
  * Entry: full position at the next 4H candle open (in live paper trading: at the close event,
    which is the next candle's open).
  * Initial stop: entry fill - 1.5 x ATR(14). R = 1.5 x ATR.
  * +1R tracking: once price reaches entry + 1R, the EMA20 exit is armed.
  * EMA20 exit: after +1R has been reached, a 4H CLOSE below EMA20 schedules a full exit at the
    next 4H open. The stop stays active until the position is closed.
  * Not used: RSI, extension filter, 20EMA entry, partials, breakeven, trailing/10-candle exit.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Iterable, Optional, Sequence

from market_data.models import Candle
from strategy.base import Signal
from strategy.indicators import atr_wilder, ema_step, highest_high

DEFAULT_PAPER_RISK = Decimal("0.15")


@dataclass(frozen=True)
class VersionAParams:
    lookback: int = 20
    atr_period: int = 14
    stop_atr_mult: Decimal = Decimal("1.5")
    risk_fraction: Decimal = DEFAULT_PAPER_RISK
    ema_fast: int = 50
    ema_slow: int = 200
    exit_ema: int = 20
    trend_filter: bool = True
    exit_after_r: Decimal = Decimal(1)

    @property
    def min_history(self) -> int:
        """Completed candles needed BEFORE the first evaluated candle (EMA200 must exist)."""
        return max(self.lookback, self.atr_period + 1, self.ema_slow if self.trend_filter else 0)


def breakout(previous: Sequence[Candle], candle: Candle, lookback: int = 20) -> Optional[Decimal]:
    """Return the breakout level if candle.close > highest high of the previous `lookback` candles."""
    if len(previous) < lookback:
        return None
    level = highest_high(previous[-lookback:])
    return level if candle.close > level else None


def trend_ok(close: Decimal, ema_fast: Decimal, ema_slow: Decimal) -> bool:
    return close > ema_slow and ema_fast > ema_slow


def ema_exit(one_r_reached: bool, close: Decimal, exit_ema: Decimal) -> bool:
    """EMA20 exit condition, evaluated at a 4H close: only after +1R has been reached."""
    return one_r_reached and close < exit_ema


class VersionA:
    name = "version_a"

    def __init__(self, params: VersionAParams = VersionAParams(), max_history: int = 2000):
        self.params = params
        self.history: deque[Candle] = deque(maxlen=max_history)
        self.ema_fast: Optional[Decimal] = None
        self.ema_slow: Optional[Decimal] = None
        self.ema_exit: Optional[Decimal] = None

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
        p = self.params
        self.ema_fast = ema_step(self.ema_fast, candle.close, p.ema_fast)
        self.ema_slow = ema_step(self.ema_slow, candle.close, p.ema_slow)
        self.ema_exit = ema_step(self.ema_exit, candle.close, p.exit_ema)

    def should_exit(self, one_r_reached: bool, candle: Candle) -> bool:
        """Call AFTER on_candle_close(candle) so EMA20 includes this close."""
        return self.ema_exit is not None and ema_exit(one_r_reached, candle.close, self.ema_exit)

    def on_candle_close(self, candle: Candle) -> Optional[Signal]:
        """Feed EVERY closed 4H candle (also while in a position). Returns ENTER_LONG on a valid breakout."""
        previous = list(self.history)
        self._append(candle)
        p = self.params
        if len(previous) < p.min_history:
            return None
        level = breakout(previous, candle, p.lookback)
        if level is None:
            return None
        if p.trend_filter and not trend_ok(candle.close, self.ema_fast, self.ema_slow):
            return None
        atr = atr_wilder(list(self.history), p.atr_period)
        if atr <= 0:
            return None
        return Signal(
            time=candle.start, action="ENTER_LONG",
            label=f"VersionA: 4H close {candle.close} > {p.lookback}-candle high {level}; trend close>EMA{p.ema_slow} "
                  f"& EMA{p.ema_fast}>EMA{p.ema_slow}; stop {p.stop_atr_mult} x ATR{p.atr_period} ({atr:.2f})",
            stop_distance=p.stop_atr_mult * atr, atr=atr, reference_price=level, candle_close=candle.close)


@dataclass(frozen=True)
class SizeDecision:
    base: Decimal
    risk_based_base: Decimal
    cash_capped: bool
    risk_usd: Decimal


def size_position(equity: Decimal, stop_distance: Decimal, price: Decimal, available_usd: Decimal,
                  taker_fee_rate: Decimal, base_increment: Decimal,
                  risk_fraction: Decimal = DEFAULT_PAPER_RISK, cash_buffer: Decimal = Decimal("0.002")) -> SizeDecision:
    """Risk `risk_fraction` of equity over `stop_distance`; available USD is the hard cap (no leverage).

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


def risk_from_env(value: Optional[str]) -> Decimal:
    """Parse PAPER_RISK_PER_TRADE (fraction of equity, e.g. 0.15). Must be in (0, 1]."""
    if value is None or not value.strip():
        return DEFAULT_PAPER_RISK
    r = Decimal(value.strip())
    if not (Decimal(0) < r <= Decimal(1)):
        raise ValueError("PAPER_RISK_PER_TRADE must be a fraction in (0, 1], e.g. 0.15")
    return r

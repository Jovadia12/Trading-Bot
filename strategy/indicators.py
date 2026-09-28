"""Indicator math on closed candles (Decimal, no look-ahead)."""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from market_data.models import Candle


def true_ranges(candles: Sequence[Candle]) -> list[Decimal]:
    """TR for each candle after the first: max(high-low, |high-prev_close|, |low-prev_close|)."""
    out = []
    for prev, c in zip(candles, candles[1:]):
        out.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
    return out


def atr_wilder(candles: Sequence[Candle], period: int = 14) -> Decimal:
    """Wilder's ATR as of the LAST candle: seed = mean of the first `period` TRs, then
    ATR_t = (ATR_{t-1} * (period-1) + TR_t) / period. Needs at least period+1 candles."""
    trs = true_ranges(candles)
    if len(trs) < period:
        raise ValueError(f"ATR({period}) needs {period + 1} candles, got {len(candles)}")
    atr = sum(trs[:period], Decimal(0)) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def highest_high(candles: Sequence[Candle]) -> Decimal:
    if not candles:
        raise ValueError("no candles")
    return max(c.high for c in candles)


def ema_step(prev: Decimal | None, value: Decimal, period: int) -> Decimal:
    """One recursive EMA step, alpha = 2/(period+1). The first value seeds the EMA
    (equivalent to pandas ``ewm(span=period, adjust=False)``)."""
    if prev is None:
        return value
    alpha = Decimal(2) / (period + 1)
    return prev + alpha * (value - prev)


def ema(values: Sequence[Decimal], period: int) -> Decimal:
    out = None
    for v in values:
        out = ema_step(out, v, period)
    if out is None:
        raise ValueError("no values")
    return out

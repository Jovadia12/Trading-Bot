"""Candle-level execution helpers for the (future) walk-forward study.

Implements the fill and cost conventions fixed in NEW_STRATEGY_RESEARCH_PLAN.md §5 so the
backtest and the live paper engine use the same definitions. No strategy logic here.
"""
from __future__ import annotations

from decimal import Decimal


def maker_fills_on_bar(side: str, limit: Decimal, bar_low: Decimal, bar_high: Decimal) -> bool:
    """Plan §5.2: a post-only order fills only if the bar trades strictly through the limit."""
    side = side.upper()
    if side == "BUY":
        return Decimal(bar_low) < Decimal(limit)
    if side == "SELL":
        return Decimal(bar_high) > Decimal(limit)
    raise ValueError(side)


def round_trip_cost_fraction(entry: str, exit: str, maker_rate: Decimal, taker_rate: Decimal,
                             taker_spread_slippage: Decimal = Decimal(0)) -> Decimal:
    """Total round-trip cost as a fraction of notional.

    entry/exit are "MAKER" or "TAKER"; ``taker_spread_slippage`` is the per-taker-leg
    half-spread + slippage (fraction), measured by market_data.spread_monitor or ASSUMED.
    """
    total = Decimal(0)
    for leg in (entry.upper(), exit.upper()):
        if leg == "MAKER":
            total += Decimal(maker_rate)
        elif leg == "TAKER":
            total += Decimal(taker_rate) + Decimal(taker_spread_slippage)
        else:
            raise ValueError(leg)
    return total


def min_gross_move_required(round_trip_cost: Decimal, safety_multiple: Decimal = Decimal(1)) -> Decimal:
    """Minimum gross expected move per trade to break even (x safety multiple)."""
    return Decimal(round_trip_cost) * Decimal(safety_multiple)

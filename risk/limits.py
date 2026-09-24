"""Pre-trade risk checks for the paper engine (no strategy logic here)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


class RiskRejected(Exception):
    pass


@dataclass(frozen=True)
class RiskLimits:
    max_order_notional_usd: Decimal = Decimal(500)     # never more than the $500 research account
    max_open_orders: int = 2
    long_only: bool = True                              # cash-only spot: no shorting
    max_drawdown_fraction: Optional[Decimal] = Decimal("0.35")   # halt new entries beyond this (plan §9)

    def check_new_order(self, *, side: str, notional: Decimal, open_orders: int,
                        position_base: Decimal, sell_base: Decimal = Decimal(0),
                        equity: Optional[Decimal] = None, peak_equity: Optional[Decimal] = None) -> None:
        if notional > self.max_order_notional_usd:
            raise RiskRejected(f"order notional {notional:.2f} exceeds limit {self.max_order_notional_usd}")
        if open_orders >= self.max_open_orders:
            raise RiskRejected(f"too many open orders ({open_orders})")
        if self.long_only and side == "SELL" and sell_base > position_base:
            raise RiskRejected("long-only: cannot sell more BTC than held")
        if (side == "BUY" and self.max_drawdown_fraction is not None and equity is not None
                and peak_equity and equity < peak_equity * (1 - self.max_drawdown_fraction)):
            raise RiskRejected("drawdown halt: new entries disabled")

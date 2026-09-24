from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


class Side(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


class OrderType(str, enum.Enum):
    MARKET = "MARKET"                      # taker (IOC against the book)
    LIMIT_POST_ONLY = "LIMIT_POST_ONLY"    # maker (rests; never takes)


class Liquidity(str, enum.Enum):
    MAKER = "MAKER"
    TAKER = "TAKER"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"          # submitted, inside the latency window
    OPEN = "OPEN"                # resting maker order
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"      # by user, or unfilled remainder of a taker order
    EXPIRED = "EXPIRED"          # maker order reached its time-to-live unfilled/partly filled
    REJECTED = "REJECTED"

    @property
    def terminal(self) -> bool:
        return self in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.REJECTED)


@dataclass
class PaperOrder:
    order_id: str
    side: Side
    order_type: OrderType
    submitted_at: datetime
    active_at: datetime
    signal: str
    base_size: Optional[Decimal] = None        # requested base (sell, or limit)
    quote_size: Optional[Decimal] = None       # requested quote (market buy)
    limit_price: Optional[Decimal] = None
    expire_at: Optional[datetime] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_base: Decimal = Decimal(0)
    filled_notional: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)
    mid_at_submit: Optional[Decimal] = None
    queue_ahead: Decimal = Decimal(0)
    hold_usd: Decimal = Decimal(0)
    hold_base: Decimal = Decimal(0)
    reason: str = ""
    closed_at: Optional[datetime] = None

    @property
    def remaining_base(self) -> Decimal:
        return (self.base_size or Decimal(0)) - self.filled_base

    @property
    def avg_price(self) -> Optional[Decimal]:
        return self.filled_notional / self.filled_base if self.filled_base else None

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id, "side": self.side.value, "type": self.order_type.value,
            "status": self.status.value, "signal": self.signal,
            "submitted_at": self.submitted_at.isoformat(), "active_at": self.active_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "base_size": str(self.base_size) if self.base_size is not None else None,
            "quote_size": str(self.quote_size) if self.quote_size is not None else None,
            "limit_price": str(self.limit_price) if self.limit_price is not None else None,
            "filled_base": str(self.filled_base), "avg_price": str(self.avg_price) if self.avg_price else None,
            "fees": str(self.fees), "reason": self.reason,
        }


@dataclass(frozen=True)
class Fill:
    order_id: str
    time: datetime
    side: Side
    price: Decimal
    base: Decimal
    liquidity: Liquidity
    fee: Decimal
    mid_at_submit: Decimal
    mid_at_fill: Decimal
    spread_cost: Decimal     # USD; half-spread paid (taker) or price improvement vs submit-mid (maker, usually < 0)
    slippage: Decimal        # USD; everything beyond half-spread: latency drift, depth, configured extra bps
    signal: str

    @property
    def notional(self) -> Decimal:
        return self.price * self.base

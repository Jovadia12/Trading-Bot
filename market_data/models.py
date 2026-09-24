from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Optional

_FRACTION = re.compile(r"\.(\d+)")


def D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def parse_time(value) -> datetime:
    """Parse Coinbase RFC3339 timestamps (nanosecond precision allowed) or epoch seconds."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    m = _FRACTION.search(s)
    if m:  # Coinbase can send nanoseconds; Python keeps microseconds
        s = s[:m.start()] + "." + m.group(1)[:6].ljust(6, "0") + s[m.end():]
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class ProductSpec:
    product_id: str
    base_currency: str
    quote_currency: str
    base_increment: Decimal
    quote_increment: Decimal
    price_increment: Decimal
    base_min_size: Decimal
    base_max_size: Decimal
    quote_min_size: Decimal
    status: str = "online"
    trading_disabled: bool = False

    @classmethod
    def from_api(cls, p: dict) -> "ProductSpec":
        return cls(
            product_id=p["product_id"],
            base_currency=p.get("base_currency_id") or p.get("base_currency") or p["product_id"].split("-")[0],
            quote_currency=p.get("quote_currency_id") or p.get("quote_currency") or p["product_id"].split("-")[1],
            base_increment=D(p.get("base_increment", "0.00000001")),
            quote_increment=D(p.get("quote_increment", "0.01")),
            price_increment=D(p.get("price_increment") or p.get("quote_increment", "0.01")),
            base_min_size=D(p.get("base_min_size", "0")),
            base_max_size=D(p.get("base_max_size", "1000000")),
            quote_min_size=D(p.get("quote_min_size", "0")),
            status=str(p.get("status", "online")),
            trading_disabled=bool(p.get("trading_disabled", False)),
        )


@dataclass(frozen=True)
class Quote:
    product_id: str
    time: datetime
    bid: Decimal
    bid_size: Decimal
    ask: Decimal
    ask_size: Decimal

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> Decimal:
        return spread_bps(self.bid, self.ask)


@dataclass(frozen=True)
class MarketTrade:
    product_id: str
    time: datetime
    price: Decimal
    size: Decimal
    side: str          # as reported by Coinbase; the fill model uses price only
    trade_id: Optional[str] = None


@dataclass(frozen=True)
class Candle:
    start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def spread_bps(bid: Decimal, ask: Decimal) -> Decimal:
    """Quoted spread in basis points of the mid price."""
    bid, ask = D(bid), D(ask)
    if bid <= 0 or ask <= 0:
        raise ValueError("bid/ask must be positive")
    mid = (bid + ask) / 2
    return (ask - bid) / mid * Decimal(10000)

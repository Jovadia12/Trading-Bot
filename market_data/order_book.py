"""Level-2 order book maintained from Coinbase Advanced ``level2`` snapshots/updates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from market_data.models import D, spread_bps

BID_SIDES = {"bid", "buy"}
ASK_SIDES = {"offer", "ask", "sell"}


@dataclass(frozen=True)
class BookWalk:
    """Result of sweeping one side of the book for a marketable order."""
    filled_base: Decimal
    notional: Decimal
    vwap: Optional[Decimal]
    touch: Optional[Decimal]
    levels_used: int
    complete: bool


class L2OrderBook:
    def __init__(self, product_id: str = "BTC-USD"):
        self.product_id = product_id
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.last_update: Optional[datetime] = None
        self.ready = False  # True after a snapshot

    # ---- maintenance -----------------------------------------------------------------------
    def clear(self) -> None:
        self.bids.clear(); self.asks.clear(); self.ready = False

    def apply(self, side: str, price, quantity, time: Optional[datetime] = None) -> None:
        side = side.lower()
        book = self.bids if side in BID_SIDES else self.asks if side in ASK_SIDES else None
        if book is None:
            raise ValueError(f"unknown book side {side!r}")
        p, q = D(price), D(quantity)
        if q == 0:
            book.pop(p, None)
        else:
            book[p] = q  # Coinbase sends the new absolute size, not a delta
        if time is not None:
            self.last_update = time

    def load_snapshot(self, updates: list[dict], time: Optional[datetime] = None) -> None:
        self.clear()
        for u in updates:
            self.apply(u["side"], u["price_level"], u["new_quantity"])
        self.last_update = time
        self.ready = True

    def load_levels(self, bids, asks, time: Optional[datetime] = None) -> None:
        """Load from a REST product_book response (lists of (price, size))."""
        self.clear()
        for p, s in bids:
            self.bids[D(p)] = D(s)
        for p, s in asks:
            self.asks[D(p)] = D(s)
        self.last_update = time
        self.ready = True

    # ---- queries -----------------------------------------------------------------------
    def best_bid(self) -> Optional[tuple[Decimal, Decimal]]:
        if not self.bids:
            return None
        p = max(self.bids)
        return p, self.bids[p]

    def best_ask(self) -> Optional[tuple[Decimal, Decimal]]:
        if not self.asks:
            return None
        p = min(self.asks)
        return p, self.asks[p]

    def mid(self) -> Optional[Decimal]:
        b, a = self.best_bid(), self.best_ask()
        return (b[0] + a[0]) / 2 if b and a else None

    def spread_bps(self) -> Optional[Decimal]:
        b, a = self.best_bid(), self.best_ask()
        return spread_bps(b[0], a[0]) if b and a else None

    def is_crossed(self) -> bool:
        b, a = self.best_bid(), self.best_ask()
        return bool(b and a and b[0] >= a[0])

    def size_at(self, side: str, price) -> Decimal:
        book = self.bids if side.lower() in BID_SIDES else self.asks
        return book.get(D(price), Decimal(0))

    def walk(self, taker_side: str, base_size: Optional[Decimal] = None,
             quote_size: Optional[Decimal] = None) -> BookWalk:
        """Sweep the opposite side for a taker BUY (asks) or SELL (bids).

        Exactly one of base_size / quote_size must be given. Partial result if depth runs out.
        """
        if (base_size is None) == (quote_size is None):
            raise ValueError("give exactly one of base_size or quote_size")
        buy = taker_side.upper() == "BUY"
        levels = sorted(self.asks.items()) if buy else sorted(self.bids.items(), reverse=True)
        remaining_base = D(base_size) if base_size is not None else None
        remaining_quote = D(quote_size) if quote_size is not None else None
        filled = notional = Decimal(0)
        used = 0
        for price, size in levels:
            if remaining_base is not None:
                take = min(size, remaining_base)
                remaining_base -= take
            else:
                take = min(size, remaining_quote / price)
                remaining_quote -= take * price
            if take <= 0:
                break
            filled += take
            notional += take * price
            used += 1
            if (remaining_base is not None and remaining_base <= 0) or (remaining_quote is not None and remaining_quote <= Decimal("1e-12")):
                break
        complete = (remaining_base is not None and remaining_base <= 0) or \
                   (remaining_quote is not None and remaining_quote <= Decimal("1e-12"))
        touch = levels[0][0] if levels else None
        return BookWalk(filled, notional, notional / filled if filled else None, touch, used, complete)

"""Paper execution engine: realistic simulated fills against live/replayed Coinbase market data.

This module has NO dependency on the exchange layer and performs no network I/O. It only
consumes order-book and trade events and mutates an in-memory ``PaperAccount``.

Execution model (see COINBASE_PAPER_TRADING.md for rationale):
* Latency: every order becomes active ``latency_ms`` after submission (event-time clock).
* Taker (MARKET): at activation, sweep the opposite side of the current L2 book (VWAP), then
  apply ``taker_extra_slippage_bps`` adversely. Insufficient depth -> partial fill, remainder
  cancelled (IOC semantics).
* Maker (LIMIT_POST_ONLY): at activation, if the limit would cross the book the order is
  REJECTED (conservative; never converts to taker). Otherwise it rests with a queue position
  equal to the displayed size at its price. Trades AT the price consume the queue first, then
  fill us (partial fills possible). A trade strictly THROUGH the price means the level was
  exhausted -> the remainder fills. Queue ahead can only shrink when the displayed level shrinks.
  Optional time-to-live -> EXPIRED if not (fully) filled.
* Fees: maker/taker rate x fill notional, in USD.
* Balance, minimum size and increment rules come from the product spec; violations -> REJECTED.
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, Decimal
from typing import Callable, Optional

from config.settings import require_paper_mode
from execution.fees import FeeSchedule
from execution.models import Fill, Liquidity, OrderStatus, OrderType, PaperOrder, Side
from market_data.models import MarketTrade, ProductSpec
from market_data.order_book import L2OrderBook
from paper_trading.account import InsufficientBalance, PaperAccount
from risk.limits import RiskLimits, RiskRejected

log = logging.getLogger(__name__)
BPS = Decimal(10000)


@dataclass(frozen=True)
class PaperExecutionConfig:
    latency_ms: int = 250
    taker_extra_slippage_bps: Decimal = Decimal(0)
    maker_fill_model: str = "queue"       # "queue" or "trade_through_only" (stricter)
    default_maker_ttl_s: Optional[float] = None


def _q(value: Decimal, increment: Decimal, rounding) -> Decimal:
    return (value / increment).to_integral_value(rounding=rounding) * increment


class PaperExecutionEngine:
    """Simulated execution only. There is intentionally no method that reaches an exchange."""

    def __init__(self, product: ProductSpec, fees: FeeSchedule, account: PaperAccount,
                 config: PaperExecutionConfig = PaperExecutionConfig(), risk: Optional[RiskLimits] = None):
        require_paper_mode()
        self.product = product
        self.fees = fees
        self.account = account
        self.config = config
        self.risk = risk or RiskLimits()
        self.orders: dict[str, PaperOrder] = {}
        self.fills: list[Fill] = []
        self._book: Optional[L2OrderBook] = None
        self._ids = itertools.count(1)
        self._listeners: list[Callable[[Fill, PaperOrder], None]] = []
        self._order_listeners: list[Callable[[PaperOrder], None]] = []
        self.peak_equity: Optional[Decimal] = None

    # ---- wiring ------------------------------------------------------------------------
    def on_fill(self, cb: Callable[[Fill, PaperOrder], None]) -> None:
        self._listeners.append(cb)

    def on_order_closed(self, cb: Callable[[PaperOrder], None]) -> None:
        self._order_listeners.append(cb)

    @property
    def open_orders(self) -> list[PaperOrder]:
        return [o for o in self.orders.values() if not o.status.terminal]

    def _mid(self) -> Optional[Decimal]:
        return self._book.mid() if self._book else None

    # ---- submission ----------------------------------------------------------------------
    def submit_market(self, side: Side, *, now: datetime, signal: str,
                      base_size: Optional[Decimal] = None, quote_size: Optional[Decimal] = None) -> PaperOrder:
        """Taker order. BUY by quote_size (USD to spend) or base_size; SELL by base_size."""
        order = self._new(side, OrderType.MARKET, now, signal)
        mid = self._mid()
        if mid is None:
            return self._reject(order, now, "no market data yet")
        if side is Side.SELL and base_size is None:
            return self._reject(order, now, "market SELL requires base_size")
        if base_size is not None:
            base_size = _q(Decimal(base_size), self.product.base_increment, ROUND_DOWN)
            order.base_size = base_size
            est_notional = base_size * mid
        else:
            order.quote_size = _q(Decimal(quote_size), self.product.quote_increment, ROUND_DOWN)
            est_notional = order.quote_size
            base_size = est_notional / mid
        if (err := self._size_error(base_size, est_notional)):
            return self._reject(order, now, err)
        return self._accept(order, now, est_notional, base_size, self.fees.taker_rate)

    def submit_post_only_limit(self, side: Side, base_size: Decimal, limit_price: Decimal, *, now: datetime,
                               signal: str, ttl_s: Optional[float] = None) -> PaperOrder:
        """Maker order; rests at limit_price, never takes liquidity."""
        order = self._new(side, OrderType.LIMIT_POST_ONLY, now, signal)
        rounding = ROUND_FLOOR if side is Side.BUY else ROUND_CEILING
        order.limit_price = _q(Decimal(limit_price), self.product.price_increment, rounding)
        order.base_size = _q(Decimal(base_size), self.product.base_increment, ROUND_DOWN)
        ttl = ttl_s if ttl_s is not None else self.config.default_maker_ttl_s
        if ttl is not None:
            order.expire_at = order.active_at + timedelta(seconds=ttl)
        notional = order.base_size * order.limit_price
        if (err := self._size_error(order.base_size, notional)):
            return self._reject(order, now, err)
        return self._accept(order, now, notional, order.base_size, self.fees.maker_rate)

    def cancel(self, order_id: str, now: datetime, reason: str = "cancelled by caller") -> PaperOrder:
        order = self.orders[order_id]
        if not order.status.terminal:
            self._close(order, now, OrderStatus.CANCELLED, reason)
        return order

    # ---- market events -------------------------------------------------------------------
    def on_book(self, book: L2OrderBook, now: datetime) -> None:
        self._book = book
        if not book.ready:
            return
        self._activate_due(now)
        self._expire_due(now)
        for o in self.open_orders:
            if o.status is OrderStatus.OPEN:   # displayed level shrank -> fewer orders ahead of us
                side = "bid" if o.side is Side.BUY else "ask"
                o.queue_ahead = min(o.queue_ahead, book.size_at(side, o.limit_price))
        mid = book.mid()
        if mid is not None:
            eq = self.account.equity(mid)
            self.peak_equity = eq if self.peak_equity is None else max(self.peak_equity, eq)

    def on_trade(self, trade: MarketTrade, now: datetime) -> None:
        if self._book is not None and self._book.ready:
            self._activate_due(now)
        self._expire_due(now)
        for o in list(self.open_orders):
            if o.status is not OrderStatus.OPEN or trade.time < o.active_at:
                continue
            L = o.limit_price
            through = trade.price < L if o.side is Side.BUY else trade.price > L
            at_price = trade.price == L
            qty = Decimal(0)
            if through:
                qty = o.remaining_base
            elif at_price and self.config.maker_fill_model == "queue":
                if o.queue_ahead >= trade.size:
                    o.queue_ahead -= trade.size
                else:
                    qty = min(o.remaining_base, trade.size - o.queue_ahead)
                    o.queue_ahead = Decimal(0)
            if qty > 0:
                self._fill(o, now, L, qty, Liquidity.MAKER, touch=L)

    # ---- internals -----------------------------------------------------------------------
    def _new(self, side: Side, otype: OrderType, now: datetime, signal: str) -> PaperOrder:
        oid = f"paper-{next(self._ids):06d}"
        order = PaperOrder(oid, side, otype, now, now + timedelta(milliseconds=self.config.latency_ms), signal)
        order.mid_at_submit = self._mid()
        self.orders[oid] = order
        return order

    def _size_error(self, base: Decimal, notional: Decimal) -> str:
        p = self.product
        if p.trading_disabled:
            return f"{p.product_id} trading disabled"
        if base <= 0:
            return "size rounds to zero"
        if base < p.base_min_size:
            return f"below minimum size: {base} < base_min_size {p.base_min_size}"
        if base > p.base_max_size:
            return f"above maximum size: {base} > base_max_size {p.base_max_size}"
        if notional < p.quote_min_size:
            return f"below minimum notional: {notional:.2f} < quote_min_size {p.quote_min_size}"
        return ""

    def _accept(self, order: PaperOrder, now: datetime, notional: Decimal, base: Decimal, fee_rate: Decimal) -> PaperOrder:
        mid = self._mid() or Decimal(0)
        try:
            self.risk.check_new_order(side=order.side.value, notional=notional, open_orders=len(self.open_orders) - 1,
                                      position_base=self.account.base, sell_base=base,
                                      equity=self.account.equity(mid) if mid else None, peak_equity=self.peak_equity)
            if order.side is Side.BUY:
                order.hold_usd = notional * (1 + fee_rate)
                self.account.hold(usd=order.hold_usd)
            else:
                order.hold_base = base
                self.account.hold(base=base)
        except (InsufficientBalance, RiskRejected) as exc:
            order.hold_usd = order.hold_base = Decimal(0)
            return self._reject(order, now, str(exc))
        log.info("paper order accepted %s %s %s signal=%s", order.order_id, order.side.value,
                 order.order_type.value, order.signal)
        return order

    def _reject(self, order: PaperOrder, now: datetime, reason: str) -> PaperOrder:
        log.info("paper order rejected %s: %s", order.order_id, reason)
        return self._close(order, now, OrderStatus.REJECTED, reason)

    def _close(self, order: PaperOrder, now: datetime, status: OrderStatus, reason: str = "") -> PaperOrder:
        self.account.release(usd=order.hold_usd, base=order.hold_base)
        order.hold_usd = order.hold_base = Decimal(0)
        order.status, order.reason, order.closed_at = status, reason or order.reason, now
        for cb in self._order_listeners:
            cb(order)
        return order

    def _activate_due(self, now: datetime) -> None:
        for o in list(self.open_orders):
            if o.status is OrderStatus.PENDING and o.active_at <= now:
                if o.order_type is OrderType.MARKET:
                    self._execute_taker(o, now)
                else:
                    self._activate_maker(o, now)

    def _expire_due(self, now: datetime) -> None:
        for o in list(self.open_orders):
            if o.expire_at is not None and now >= o.expire_at:
                self._close(o, now, OrderStatus.EXPIRED,
                            "maker order unfilled at expiry" if o.filled_base == 0 else "maker order partially filled at expiry")

    def _activate_maker(self, o: PaperOrder, now: datetime) -> None:
        book = self._book
        bid, ask = book.best_bid(), book.best_ask()
        crosses = (o.side is Side.BUY and ask and o.limit_price >= ask[0]) or \
                  (o.side is Side.SELL and bid and o.limit_price <= bid[0])
        if crosses:
            self._close(o, now, OrderStatus.REJECTED, "post-only order would take liquidity")
            return
        o.status = OrderStatus.OPEN
        o.queue_ahead = book.size_at("bid" if o.side is Side.BUY else "ask", o.limit_price)

    def _execute_taker(self, o: PaperOrder, now: datetime) -> None:
        book = self._book
        if o.side is Side.BUY and o.quote_size is not None:
            walk = book.walk("BUY", quote_size=o.quote_size)
        else:
            walk = book.walk(o.side.value, base_size=o.base_size)
        base = _q(walk.filled_base, self.product.base_increment, ROUND_DOWN)
        if base <= 0 or walk.vwap is None:
            self._close(o, now, OrderStatus.CANCELLED, "no liquidity")
            return
        adj = walk.vwap * (1 + o.side.sign * self.config.taker_extra_slippage_bps / BPS)
        if o.side is Side.BUY:   # never spend more than was reserved
            max_base = _q(o.hold_usd / (adj * (1 + self.fees.taker_rate)), self.product.base_increment, ROUND_DOWN)
            base = min(base, max_base)
        if o.base_size is None:
            o.base_size = base
        self._fill(o, now, adj, base, Liquidity.TAKER, touch=walk.touch)
        if not o.status.terminal:
            self._close(o, now, OrderStatus.CANCELLED if walk.complete is False else OrderStatus.FILLED,
                        "insufficient book depth; remainder cancelled" if walk.complete is False else "")

    def _fill(self, o: PaperOrder, now: datetime, price: Decimal, base: Decimal, liq: Liquidity,
              touch: Optional[Decimal]) -> None:
        notional = price * base
        fee = self.fees.fee(notional, liq)
        mid_fill = self._mid() or price
        mid_submit = o.mid_at_submit or mid_fill
        shortfall = (price - mid_submit) * base * o.side.sign
        if liq is Liquidity.TAKER:
            spread_cost = ((touch or price) - mid_fill) * base * o.side.sign
            slippage = shortfall - spread_cost
        else:
            spread_cost, slippage = shortfall, Decimal(0)
        acct = self.account
        if o.side is Side.BUY:
            cost = notional + fee
            acct.release(usd=min(cost, o.hold_usd))
            o.hold_usd = max(Decimal(0), o.hold_usd - cost)
            acct.usd -= cost
            acct.base += base
        else:
            acct.release(base=min(base, o.hold_base))
            o.hold_base = max(Decimal(0), o.hold_base - base)
            acct.base -= base
            acct.usd += notional - fee
        o.filled_base += base
        o.filled_notional += notional
        o.fees += fee
        fill = Fill(o.order_id, now, o.side, price, base, liq, fee, mid_submit, mid_fill, spread_cost, slippage, o.signal)
        self.fills.append(fill)
        log.info("paper fill %s %s %s @ %s (%s) fee=%s", o.order_id, o.side.value, base, price, liq.value,
                 f"{fee:.4f}")
        for cb in self._listeners:
            cb(fill, o)
        if o.base_size is not None and o.remaining_base <= 0:
            self._close(o, now, OrderStatus.FILLED)

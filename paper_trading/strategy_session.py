"""Strategy paper trading: WebSocket trades -> 4H candle aggregator -> Version A -> paper engine -> recorder.

Only the paper engine is used for execution; there is no exchange client in this module.
Entries: on a 4H candle close that produces ENTER_LONG and no position is open, buy (taker,
walking the live book) a quantity sized to risk 0.5% of current equity over the 1.5 ATR stop.
Stop: armed at (entry fill VWAP - stop distance) once the entry fills; triggered by the first live
trade at or below it; exits with a taker sell of the whole position (partial fills are retried).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from exchange.client import ExchangeClient
from execution.models import OrderStatus, PaperOrder, Side
from execution.paper_engine import PaperExecutionEngine
from market_data.candle_aggregator import FOUR_HOURS, CandleAggregator, ClosedCandle, aggregate, bucket_start
from market_data.models import Candle, MarketTrade
from strategy.base import Signal
from strategy.version_a import VersionA, size_position

log = logging.getLogger(__name__)
DUST = Decimal("0.00000001")


class WarmupError(RuntimeError):
    pass


def fetch_warmup(client: ExchangeClient, product_id: str, now: datetime, n_candles: int = 60,
                 interval_s: int = FOUR_HOURS) -> tuple[list[Candle], Optional[Candle]]:
    """Completed 4H candles (oldest first) + the forming bucket so far, from 1H candles via get_candles().

    The forming candle is returned separately and is NEVER part of the historical list.
    Requests are chunked to stay under Coinbase's 350-candles-per-request limit.
    """
    current = bucket_start(now, interval_s)
    start = current - timedelta(seconds=interval_s * n_candles)
    hourly: list[Candle] = []
    chunk = timedelta(hours=300)
    t = start
    while t < now:
        end = min(t + chunk, now)
        hourly.extend(client.get_candles(product_id, t, end, "1h"))
        t = end
    seen, unique = set(), []
    for c in sorted(hourly, key=lambda c: c.start):
        if c.start not in seen:
            seen.add(c.start)
            unique.append(c)
    completed, forming = aggregate(unique, interval_s, 3600, now)
    completed = [c for c in completed if c.start + timedelta(seconds=interval_s) <= current]
    return completed, forming


@dataclass
class StrategyStats:
    warmup_candles: int = 0
    candles_closed: int = 0
    incomplete_candles: int = 0
    signals: int = 0
    signals_ignored_in_position: int = 0
    entries_submitted: int = 0
    entries_rejected: int = 0
    stops_triggered: int = 0
    events: list = field(default_factory=list)


class StrategyTrader:
    def __init__(self, strategy: VersionA, engine: PaperExecutionEngine, aggregator: CandleAggregator,
                 cash_buffer: Decimal = Decimal("0.002")):
        self.strategy, self.engine, self.agg = strategy, engine, aggregator
        self.cash_buffer = cash_buffer
        self.stats = StrategyStats()
        self.candles: list[tuple[Candle, bool]] = []
        self.stop_price: Optional[Decimal] = None
        self.pending_signal: Optional[Signal] = None
        self.entry_order: Optional[PaperOrder] = None
        self.exit_order: Optional[PaperOrder] = None
        self.last_trade_price: Optional[Decimal] = None
        engine.on_order_closed(self._on_order_closed)

    # ---- state ---------------------------------------------------------------------------------
    @property
    def in_position(self) -> bool:
        return self.engine.account.base > DUST

    def equity(self, mark: Optional[Decimal] = None) -> Decimal:
        mark = mark or self.engine._mid() or self.last_trade_price or Decimal(0)
        return self.engine.account.equity(mark)

    def _log(self, kind: str, now: datetime, **kw) -> None:
        self.stats.events.append({"time": now.isoformat(), "event": kind,
                                  **{k: str(v) for k, v in kw.items()}})
        log.info("strategy %s %s", kind, kw)

    # ---- inputs --------------------------------------------------------------------------------
    def on_trade(self, trade: MarketTrade) -> None:
        self.last_trade_price = trade.price
        for closed in self.agg.on_trade(trade):
            self._on_candle_close(closed, trade.time)
        self._check_stop(trade.price, trade.time)

    def on_tick(self, now: datetime) -> None:
        for closed in self.agg.on_time(now):
            self._on_candle_close(closed, now)

    # ---- strategy -----------------------------------------------------------------------------
    def _on_candle_close(self, closed: ClosedCandle, now: datetime) -> None:
        c = closed.candle
        self.stats.candles_closed += 1
        self.candles.append((c, closed.complete))
        if not closed.complete:
            # Session started mid-candle without a REST seed: history keeps it, but no signal is
            # evaluated on a candle we did not fully observe.
            self.stats.incomplete_candles += 1
            self.strategy._append(c)
            self._log("candle_incomplete_not_evaluated", now, start=c.start.isoformat())
            return
        signal = self.strategy.on_candle_close(c)
        self._log("candle_close", now, start=c.start.isoformat(), o=c.open, h=c.high, l=c.low, c=c.close)
        if signal is None:
            return
        self.stats.signals += 1
        if self.in_position or self.entry_order is not None:
            self.stats.signals_ignored_in_position += 1
            self._log("signal_ignored_in_position", now, label=signal.label)
            return
        self._enter(signal, now)

    def _enter(self, signal: Signal, now: datetime) -> None:
        e = self.engine
        book = e._book
        ask = book.best_ask()[0] if book and book.ready and book.best_ask() else None
        if ask is None:
            self.stats.entries_rejected += 1
            self._log("entry_skipped_no_market_data", now, label=signal.label)
            return
        decision = size_position(self.equity(), signal.stop_distance, ask, e.account.available_usd,
                                 e.fees.taker_rate, e.product.base_increment,
                                 risk_fraction=self.strategy.params.risk_fraction, cash_buffer=self.cash_buffer)
        self._log("signal", now, label=signal.label, atr=signal.atr, stop_distance=signal.stop_distance,
                  equity=self.equity(), size_btc=decision.base, risk_usd=decision.risk_usd,
                  cash_capped=decision.cash_capped)
        order = e.submit_market(Side.BUY, base_size=decision.base, now=now, signal=signal.label)
        self.stats.entries_submitted += 1
        if order.status is OrderStatus.REJECTED:
            self.stats.entries_rejected += 1
            self._log("entry_rejected", now, reason=order.reason)
            return
        self.entry_order, self.pending_signal = order, signal

    def _check_stop(self, price: Decimal, now: datetime) -> None:
        if self.stop_price is None or not self.in_position:
            return
        if self.exit_order is not None and not self.exit_order.status.terminal:
            return
        if price <= self.stop_price:
            if self.exit_order is None:
                self.stats.stops_triggered += 1
                self._log("stop_triggered", now, trade_price=price, stop=self.stop_price)
            self.exit_order = self.engine.submit_market(
                Side.SELL, base_size=self.engine.account.available_base, now=now,
                signal=f"VersionA: 1.5 ATR stop {self.stop_price:.2f} hit (trade {price})")

    # ---- engine callbacks ---------------------------------------------------------------------
    def _on_order_closed(self, order: PaperOrder) -> None:
        now = order.closed_at or datetime.now(timezone.utc)
        if self.entry_order is not None and order.order_id == self.entry_order.order_id:
            sig, self.entry_order, self.pending_signal = self.pending_signal, None, None
            if order.filled_base > 0:
                self.stop_price = order.avg_price - sig.stop_distance
                self._log("entry_filled", now, qty=order.filled_base, price=order.avg_price,
                          fees=order.fees, stop=self.stop_price, status=order.status.value)
            else:
                self.stats.entries_rejected += 1
                self._log("entry_not_filled", now, reason=order.reason)
        elif self.exit_order is not None and order.order_id == self.exit_order.order_id:
            self._log("exit_order_closed", now, qty=order.filled_base, price=order.avg_price,
                      fees=order.fees, status=order.status.value)
            if not self.in_position:
                self.stop_price, self.exit_order = None, None
            # else: remainder stays open; the next trade at/below the stop re-submits the exit

    # ---- output -------------------------------------------------------------------------------
    def snapshot(self) -> dict:
        acct = self.engine.account
        mark = self.engine._mid() or self.last_trade_price
        return {
            "strategy": self.strategy.name, "params": {k: str(v) for k, v in vars(self.strategy.params).items()},
            "warmup_candles": self.stats.warmup_candles, "candles_closed_live": self.stats.candles_closed,
            "incomplete_candles": self.stats.incomplete_candles, "signals": self.stats.signals,
            "signals_ignored_in_position": self.stats.signals_ignored_in_position,
            "entries_submitted": self.stats.entries_submitted, "entries_rejected": self.stats.entries_rejected,
            "stops_triggered": self.stats.stops_triggered,
            "position_btc": str(acct.base), "stop_price": str(self.stop_price) if self.stop_price else None,
            "usd": f"{acct.usd:.2f}", "equity_usd": f"{self.equity(mark):.2f}" if mark else None,
            "mark_price": str(mark) if mark else None,
        }

    def write(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / "candles_4h.csv", "w") as fh:
            fh.write("start,open,high,low,close,volume,complete\n")
            for c, ok in self.candles:
                fh.write(f"{c.start.isoformat()},{c.open},{c.high},{c.low},{c.close},{c.volume},{ok}\n")
        with open(directory / "strategy_events.jsonl", "w") as fh:
            for e in self.stats.events:
                fh.write(json.dumps(e) + "\n")

"""Coinbase Advanced Trade WebSocket market-data feed (public channels only).

Channels: ``heartbeats`` (keeps the connection open), ``level2`` (order book), ``market_trades``
and ``ticker``. Subscribe format follows the official SDK: one message per channel,
``{"type": "subscribe", "product_ids": [...], "channel": "<name>"}``. No JWT is sent: these
channels are public, so the market-data connection never carries credentials.

Parsing is pure (``parse_message``) so it can be unit-tested and replayed from recorded files.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Iterable, Optional

from exchange.endpoints import WS_MARKET_DATA_URL
from market_data.models import D, MarketTrade, Quote, parse_time
from market_data.order_book import L2OrderBook

log = logging.getLogger(__name__)

DEFAULT_CHANNELS = ("heartbeats", "level2", "market_trades", "ticker")


@dataclass
class FeedEvent:
    kind: str                       # "book", "trade", "ticker", "heartbeat", "subscriptions", "error", "gap"
    time: Optional[datetime]
    payload: Any = None


@dataclass
class FeedState:
    book: L2OrderBook
    last_sequence: Optional[int] = None
    gaps: int = 0
    messages: int = 0
    last_ticker: Optional[Quote] = None
    last_trade: Optional[MarketTrade] = None
    errors: list = field(default_factory=list)


def subscribe_messages(product_ids: Iterable[str], channels: Iterable[str] = DEFAULT_CHANNELS) -> list[dict]:
    return [{"type": "subscribe", "product_ids": list(product_ids), "channel": ch} for ch in channels]


def parse_message(raw: str | dict, state: FeedState) -> list[FeedEvent]:
    """Update ``state`` from one WebSocket message and return normalized events."""
    msg = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    state.messages += 1
    events: list[FeedEvent] = []
    if msg.get("type") == "error":
        state.errors.append(msg.get("message"))
        return [FeedEvent("error", None, msg.get("message"))]

    seq = msg.get("sequence_num")
    if seq is not None:
        if state.last_sequence is not None and seq != state.last_sequence + 1:
            state.gaps += 1
            events.append(FeedEvent("gap", None, {"expected": state.last_sequence + 1, "got": seq}))
        state.last_sequence = seq

    channel = msg.get("channel")
    ts = parse_time(msg["timestamp"]) if msg.get("timestamp") else None
    for ev in msg.get("events", []):
        if channel == "l2_data":
            updates = ev.get("updates", [])
            if ev.get("type") == "snapshot":
                state.book.load_snapshot(updates, ts)
            else:
                for u in updates:
                    state.book.apply(u["side"], u["price_level"], u["new_quantity"], ts)
            events.append(FeedEvent("book", ts, state.book))
        elif channel == "market_trades":
            for t in ev.get("trades", []):
                trade = MarketTrade(t.get("product_id", state.book.product_id), parse_time(t["time"]),
                                    D(t["price"]), D(t["size"]), str(t.get("side", "")), t.get("trade_id"))
                state.last_trade = trade
                events.append(FeedEvent("trade", trade.time, trade))
        elif channel == "ticker":
            for t in ev.get("tickers", []):
                if t.get("best_bid") and t.get("best_ask"):
                    q = Quote(t.get("product_id", state.book.product_id), ts, D(t["best_bid"]),
                              D(t.get("best_bid_quantity", "0")), D(t["best_ask"]), D(t.get("best_ask_quantity", "0")))
                    state.last_ticker = q
                    events.append(FeedEvent("ticker", ts, q))
        elif channel == "heartbeats":
            events.append(FeedEvent("heartbeat", ts, ev.get("heartbeat_counter")))
        elif channel == "subscriptions":
            events.append(FeedEvent("subscriptions", ts, ev.get("subscriptions")))
    return events


class SessionClock:
    """Deadline that holds even if the machine sleeps or the event loop is starved.

    Elapsed time is the MAX of monotonic and wall-clock elapsed: on macOS the monotonic clock can
    pause during system sleep, while the wall clock keeps counting.
    """

    def __init__(self, duration: Optional[float]):
        self.duration = duration
        self._m0, self._w0 = time.monotonic(), time.time()

    def elapsed(self) -> float:
        return max(time.monotonic() - self._m0, time.time() - self._w0)

    def remaining(self) -> float:
        return float("inf") if self.duration is None else self.duration - self.elapsed()

    def expired(self) -> bool:
        return self.remaining() <= 0


CLOSE_TIMEOUT_S = 2.0      # bounded WebSocket close handshake; then the TCP transport is aborted


async def close_websocket(ws) -> None:
    """Close without ever hanging: graceful close bounded by CLOSE_TIMEOUT_S, else abort the socket."""
    if ws is None:
        return
    try:
        await asyncio.wait_for(ws.close(), timeout=CLOSE_TIMEOUT_S + 0.5)
    except BaseException:  # noqa: BLE001 - includes CancelledError/TimeoutError; fall through to abort
        pass
    transport = getattr(ws, "transport", None)
    if transport is not None and not transport.is_closing():
        transport.abort()


class CoinbaseMarketDataFeed:
    """Async public market-data stream with reconnect + resubscribe on gaps/timeouts.

    ``stream(stop_after=N)`` never runs past N seconds of wall-clock *or* monotonic time: every
    wait (connect, receive, reconnect backoff) is capped at the time remaining, and the socket is
    closed with a bounded handshake. Callers may also cancel the consuming task at any time; the
    connection is then closed the same bounded way.
    """

    def __init__(self, product_id: str = "BTC-USD", channels: Iterable[str] = DEFAULT_CHANNELS,
                 url: str = WS_MARKET_DATA_URL, idle_timeout: float = 30.0, max_retries: int = 5):
        self.product_id = product_id
        self.channels = tuple(channels)
        self.url = url
        self.idle_timeout = idle_timeout
        self.max_retries = max_retries
        self.state = FeedState(L2OrderBook(product_id))
        self.connections = 0

    async def stream(self, stop_after: Optional[float] = None,
                     clock: Optional[SessionClock] = None) -> AsyncIterator[FeedEvent]:
        import websockets  # imported lazily so pure parsing works without the dependency

        clock = clock or SessionClock(stop_after)
        attempt = 0
        while not clock.expired():
            ws = None
            try:
                ws = await websockets.connect(
                    self.url, max_size=None, open_timeout=max(0.5, min(10.0, clock.remaining())),
                    close_timeout=CLOSE_TIMEOUT_S, ping_interval=20, ping_timeout=20)
                self.connections += 1
                for m in subscribe_messages([self.product_id], self.channels):
                    await ws.send(json.dumps(m))
                self.state.last_sequence = None
                attempt = 0
                while True:
                    remaining = clock.remaining()
                    if remaining <= 0:
                        return
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=min(self.idle_timeout, remaining))
                    except asyncio.TimeoutError:
                        if clock.expired():
                            return
                        log.warning("market-data feed idle for %.0fs; reconnecting", self.idle_timeout)
                        break
                    resync = False
                    for ev in parse_message(raw, self.state):
                        if ev.kind == "gap":
                            log.warning("sequence gap %s; resubscribing for a fresh snapshot", ev.payload)
                            self.state.book.clear()
                            resync = True
                        yield ev
                    if resync:
                        break
            except Exception as exc:  # noqa: BLE001 - reconnect on any feed failure
                if clock.expired():
                    return
                attempt += 1
                self.state.errors.append(f"{type(exc).__name__}: {exc}")
                if attempt > self.max_retries:
                    raise
                wait = min(30.0, 2.0 * 1.5 ** attempt, max(0.0, clock.remaining()))
                log.warning("feed connection error (%s); retry %d/%d in %.1fs", type(exc).__name__,
                            attempt, self.max_retries, wait)
                await asyncio.sleep(wait)
            finally:
                await close_websocket(ws)


def replay_file(path: str, product_id: str = "BTC-USD") -> Iterable[FeedEvent]:
    """Replay recorded WebSocket messages (one JSON message per line)."""
    state = FeedState(L2OrderBook(product_id))
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                yield from parse_message(line, state)

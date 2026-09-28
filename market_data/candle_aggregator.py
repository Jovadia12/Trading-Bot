"""Build fixed-interval (default 4H, UTC-aligned) candles from WebSocket trade events.

* Buckets are [k*interval, (k+1)*interval) in UTC epoch seconds (4H -> 00,04,08,12,16,20 UTC).
* A bucket is emitted EXACTLY ONCE, when (a) a trade at/after its end arrives, or (b) the clock
  passes its end + grace (so a quiet market still closes the candle).
* If whole buckets pass with no trades, one flat candle (volume 0) is emitted per missed bucket,
  so there is exactly one closed candle per boundary.
* Trades older than the open bucket (late/duplicate) are ignored and counted.
* ``seed()`` pre-loads the currently forming bucket (e.g. from REST 1H candles) so a session
  started mid-candle still produces a complete first candle; without a seed that first candle
  is marked incomplete.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional

from market_data.models import Candle, MarketTrade

FOUR_HOURS = 4 * 3600


def bucket_start(t: datetime, interval_s: int = FOUR_HOURS) -> datetime:
    epoch = int(t.timestamp())
    return datetime.fromtimestamp(epoch - epoch % interval_s, tz=timezone.utc)


@dataclass(frozen=True)
class ClosedCandle:
    candle: Candle
    complete: bool          # False if the session started mid-bucket without a seed
    trades: int


class CandleAggregator:
    def __init__(self, interval_s: int = FOUR_HOURS, grace_s: float = 2.0):
        self.interval = timedelta(seconds=interval_s)
        self.interval_s = interval_s
        self.grace = timedelta(seconds=grace_s)
        self._start: Optional[datetime] = None
        self._o = self._h = self._l = self._c = None
        self._v = Decimal(0)
        self._n = 0
        self._complete = True
        self._as_of: Optional[datetime] = None
        self._seen: deque = deque(maxlen=5000)
        self._seen_set: set = set()
        self.late_trades = 0
        self.last_close: Optional[Decimal] = None
        self.emitted: list[datetime] = []

    # ---- setup -----------------------------------------------------------------------------
    def seed(self, partial: Candle, as_of: datetime) -> None:
        """Forming bucket so far (from REST). Trades before ``as_of`` are then ignored (already counted)."""
        self._start = bucket_start(partial.start, self.interval_s)
        self._o, self._h, self._l, self._c, self._v = partial.open, partial.high, partial.low, partial.close, partial.volume
        self._n, self._complete, self._as_of = 0, True, as_of

    def set_last_close(self, close: Decimal) -> None:
        """Close of the last completed (historical) candle, used for flat candles if nothing trades."""
        self.last_close = close

    # ---- events ----------------------------------------------------------------------------
    def on_trade(self, trade: MarketTrade) -> list[ClosedCandle]:
        if trade.trade_id:
            if trade.trade_id in self._seen_set:
                self.late_trades += 1
                return []
            if len(self._seen) == self._seen.maxlen:
                self._seen_set.discard(self._seen[0])
            self._seen.append(trade.trade_id)
            self._seen_set.add(trade.trade_id)
        if self._as_of is not None and trade.time < self._as_of:
            return []                                  # already inside the REST seed
        b = bucket_start(trade.time, self.interval_s)
        closed: list[ClosedCandle] = []
        if self._start is None:
            self._open_bucket(b, complete=(trade.time == b))   # started mid-bucket -> incomplete
        elif b < self._start:
            self.late_trades += 1
            return []
        elif b > self._start:
            closed = self._roll_to(b)
        p, q = trade.price, trade.size
        if self._o is None:
            self._o = self._h = self._l = self._c = p
        else:
            self._h, self._l, self._c = max(self._h, p), min(self._l, p), p
        self._v += q
        self._n += 1
        return closed

    def on_time(self, now: datetime) -> list[ClosedCandle]:
        """Close buckets whose end (+grace) has passed even if no trade arrived."""
        if self._start is None:
            return []
        if now >= self._start + self.interval + self.grace:
            return self._roll_to(bucket_start(now - self.grace, self.interval_s))
        return []

    # ---- internals ---------------------------------------------------------------------------
    def _open_bucket(self, start: datetime, complete: bool) -> None:
        self._start, self._complete = start, complete
        self._o = self._h = self._l = self._c = None
        self._v, self._n = Decimal(0), 0

    def _emit_current(self) -> Optional[ClosedCandle]:
        if self._o is None:
            if self.last_close is None:
                return None
            price = self.last_close
            candle = Candle(self._start, price, price, price, price, Decimal(0))
        else:
            candle = Candle(self._start, self._o, self._h, self._l, self._c, self._v)
        if self.emitted and self.emitted[-1] >= self._start:
            return None                                # never emit the same boundary twice
        self.emitted.append(self._start)
        self.last_close = candle.close
        return ClosedCandle(candle, self._complete, self._n)

    def _roll_to(self, new_start: datetime) -> list[ClosedCandle]:
        out: list[ClosedCandle] = []
        while self._start < new_start:
            c = self._emit_current()
            if c:
                out.append(c)
            self._open_bucket(self._start + self.interval, complete=True)
        return out


def aggregate(candles: Iterable[Candle], interval_s: int = FOUR_HOURS, source_s: int = 3600,
              now: Optional[datetime] = None) -> tuple[list[Candle], Optional[Candle]]:
    """Combine smaller candles (e.g. 1H) into interval candles.

    Returns (completed, forming): ``completed`` only contains buckets whose end <= now AND that
    contain every source candle (no gaps); ``forming`` is the bucket that contains ``now``.
    """
    now = now or datetime.now(timezone.utc)
    per = interval_s // source_s
    groups: dict[datetime, list[Candle]] = {}
    for c in sorted(candles, key=lambda c: c.start):
        groups.setdefault(bucket_start(c.start, interval_s), []).append(c)
    completed, forming = [], None
    for start, cs in sorted(groups.items()):
        merged = Candle(start, cs[0].open, max(c.high for c in cs), min(c.low for c in cs), cs[-1].close,
                        sum((c.volume for c in cs), Decimal(0)))
        end = start + timedelta(seconds=interval_s)
        if end <= now:
            if len(cs) == per:
                completed.append(merged)
        elif start <= now:
            forming = merged
    return completed, forming

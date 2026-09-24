"""Spread and taker-slippage measurement from the live (or replayed) order book.

For each sample it records the quoted spread (bps of mid) and, for configurable notionals
(default $250 and $500), the cost of an immediate taker BUY and SELL measured against mid:
``half-spread + depth impact``, in bps. These are *measured* numbers for the research plan,
replacing the "ASSUMED" spread/slippage scenarios once enough samples exist.
"""
from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from market_data.order_book import L2OrderBook

BPS = Decimal(10000)


@dataclass
class SpreadSample:
    time: datetime
    bid: Decimal
    ask: Decimal
    mid: Decimal
    spread_bps: Decimal
    taker_cost_bps: dict = field(default_factory=dict)   # {"buy_250": bps, "sell_500": bps, ...}


class SpreadMonitor:
    def __init__(self, notionals=(Decimal(250), Decimal(500)), min_interval_s: float = 1.0):
        self.notionals = tuple(Decimal(n) for n in notionals)
        self.min_interval_s = min_interval_s
        self.samples: list[SpreadSample] = []
        self._last: Optional[datetime] = None

    def sample(self, book: L2OrderBook, time: datetime) -> Optional[SpreadSample]:
        if not book.ready or book.is_crossed():
            return None
        if self._last and (time - self._last).total_seconds() < self.min_interval_s:
            return None
        b, a = book.best_bid(), book.best_ask()
        if not b or not a:
            return None
        mid = (b[0] + a[0]) / 2
        costs = {}
        for n in self.notionals:
            buy = book.walk("BUY", quote_size=n)
            sell_base = n / mid
            sell = book.walk("SELL", base_size=sell_base)
            if buy.complete and buy.vwap:
                costs[f"buy_{int(n)}"] = (buy.vwap - mid) / mid * BPS
            if sell.complete and sell.vwap:
                costs[f"sell_{int(n)}"] = (mid - sell.vwap) / mid * BPS
        s = SpreadSample(time, b[0], a[0], mid, book.spread_bps(), costs)
        self.samples.append(s)
        self._last = time
        return s

    def summary(self) -> dict:
        if not self.samples:
            return {"samples": 0}

        def pct(values, q):
            values = sorted(values)
            if len(values) == 1:
                return values[0]
            k = (len(values) - 1) * q
            lo, hi = int(k), min(int(k) + 1, len(values) - 1)
            return values[lo] + (values[hi] - values[lo]) * (k - lo)

        sp = [float(s.spread_bps) for s in self.samples]
        out = {
            "samples": len(sp),
            "from": self.samples[0].time.isoformat(),
            "to": self.samples[-1].time.isoformat(),
            "spread_bps_median": statistics.median(sp),
            "spread_bps_p90": pct(sp, 0.9),
            "spread_bps_max": max(sp),
        }
        keys = sorted({k for s in self.samples for k in s.taker_cost_bps})
        for k in keys:
            vals = [float(s.taker_cost_bps[k]) for s in self.samples if k in s.taker_cost_bps]
            out[f"taker_{k}_bps_median"] = statistics.median(vals)
            out[f"taker_{k}_bps_p90"] = pct(vals, 0.9)
            out[f"taker_{k}_bps_max"] = max(vals)
        return out

    def to_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        keys = sorted({k for s in self.samples for k in s.taker_cost_bps})
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["time", "bid", "ask", "mid", "spread_bps", *[f"taker_{k}_bps" for k in keys]])
            for s in self.samples:
                w.writerow([s.time.isoformat(), s.bid, s.ask, s.mid, f"{s.spread_bps:.4f}",
                            *[f"{s.taker_cost_bps[k]:.4f}" if k in s.taker_cost_bps else "" for k in keys]])

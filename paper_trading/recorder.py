"""Builds round-trip trade records from paper fills and writes them to disk.

A round trip opens on the first BUY fill from flat and closes when the position returns to
flat. Entry/exit prices are fill VWAPs. ``gross_pnl`` uses fill prices (so spread and slippage
are already inside it); ``spread_cost`` and ``slippage`` are reported as components of that
execution drag and are NOT subtracted a second time. ``net_pnl = gross_pnl - fees``.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from execution.models import Fill, Liquidity, PaperOrder, Side

DUST = Decimal("0.00000001")


@dataclass
class ClosedTrade:
    timestamp: str           # exit (close) time
    entry_time: str
    side: str                # LONG (cash-only spot)
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    gross_pnl: Decimal
    fees: Decimal
    spread_cost: Decimal
    slippage: Decimal
    net_pnl: Decimal
    holding_seconds: float
    entry_signal: str
    exit_signal: str
    execution_type: str      # e.g. MAKER/TAKER (entry/exit liquidity)


class _Leg:
    def __init__(self):
        self.base = Decimal(0); self.notional = Decimal(0); self.fees = Decimal(0)
        self.spread = Decimal(0); self.slip = Decimal(0); self.liq: set[str] = set()
        self.signal = ""; self.first: Optional[datetime] = None; self.last: Optional[datetime] = None

    def add(self, f: Fill):
        self.base += f.base; self.notional += f.notional; self.fees += f.fee
        self.spread += f.spread_cost; self.slip += f.slippage; self.liq.add(f.liquidity.value)
        self.signal = self.signal or f.signal
        self.first = self.first or f.time; self.last = f.time

    @property
    def vwap(self) -> Decimal:
        return self.notional / self.base

    @property
    def liquidity(self) -> str:
        return next(iter(self.liq)) if len(self.liq) == 1 else "MIXED" if self.liq else ""


class TradeRecorder:
    def __init__(self):
        self.trades: list[ClosedTrade] = []
        self.orders: list[dict] = []
        self._entry: Optional[_Leg] = None
        self._exit: Optional[_Leg] = None
        self._position = Decimal(0)

    def on_fill(self, fill: Fill, order: PaperOrder) -> None:
        if fill.side is Side.BUY:
            if self._entry is None:
                self._entry = _Leg()
            self._entry.add(fill)
            self._position += fill.base
        else:
            if self._entry is None:
                return  # selling pre-existing inventory is outside round-trip accounting
            if self._exit is None:
                self._exit = _Leg()
            self._exit.add(fill)
            self._position -= fill.base
            if self._position <= DUST:
                self._close()

    def on_order_closed(self, order: PaperOrder) -> None:
        self.orders.append(order.to_dict())

    def _close(self) -> None:
        e, x = self._entry, self._exit
        qty = min(e.base, x.base)
        entry_px, exit_px = e.vwap, x.vwap
        gross = (exit_px - entry_px) * qty
        fees = e.fees + x.fees
        self.trades.append(ClosedTrade(
            timestamp=x.last.isoformat(), entry_time=e.first.isoformat(), side="LONG",
            entry_price=entry_px, exit_price=exit_px, quantity=qty, gross_pnl=gross, fees=fees,
            spread_cost=e.spread + x.spread, slippage=e.slip + x.slip, net_pnl=gross - fees,
            holding_seconds=(x.last - e.first).total_seconds(), entry_signal=e.signal, exit_signal=x.signal,
            execution_type=f"{e.liquidity}/{x.liquidity}",
        ))
        self._entry = self._exit = None
        self._position = Decimal(0)

    # ---- output ---------------------------------------------------------------------------
    def write(self, directory: Path) -> dict[str, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        trades_csv, orders_jsonl = directory / "trades.csv", directory / "orders.jsonl"
        fields = list(ClosedTrade.__dataclass_fields__)
        with open(trades_csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for t in self.trades:
                w.writerow({k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(t).items()})
        with open(orders_jsonl, "w") as fh:
            for o in self.orders:
                fh.write(json.dumps(o) + "\n")
        return {"trades": trades_csv, "orders": orders_jsonl}

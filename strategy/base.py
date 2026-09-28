from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Protocol

from market_data.models import Candle


@dataclass(frozen=True)
class Signal:
    time: datetime
    action: str              # "ENTER_LONG" | "EXIT_LONG"
    label: str               # human-readable rule that fired, recorded on every paper trade
    limit_price: Optional[float] = None
    # Protective-stop information for strategies that define one (Version A: 1.5 x ATR).
    stop_distance: Optional[Decimal] = None   # price distance below the entry fill
    atr: Optional[Decimal] = None
    reference_price: Optional[Decimal] = None  # e.g. the breakout level
    candle_close: Optional[Decimal] = None


class Strategy(Protocol):
    """A frozen strategy maps closed candles to signals. It never sees the exchange client."""

    name: str

    def on_candle_close(self, candle: Candle) -> Optional[Signal]: ...

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from market_data.models import Candle


@dataclass(frozen=True)
class Signal:
    time: datetime
    action: str              # "ENTER_LONG" | "EXIT_LONG"
    label: str               # human-readable rule that fired, recorded on every paper trade
    limit_price: Optional[float] = None


class Strategy(Protocol):
    """A frozen strategy maps closed candles to signals. It never sees the exchange client."""

    name: str

    def on_candle_close(self, candle: Candle) -> Optional[Signal]: ...

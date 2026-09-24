from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class InsufficientBalance(Exception):
    pass


@dataclass
class PaperAccount:
    """Cash-only spot account. Holds reserve funds for open/pending orders."""
    usd: Decimal = Decimal(500)
    base: Decimal = Decimal(0)
    held_usd: Decimal = Decimal(0)
    held_base: Decimal = Decimal(0)

    @property
    def available_usd(self) -> Decimal:
        return self.usd - self.held_usd

    @property
    def available_base(self) -> Decimal:
        return self.base - self.held_base

    def hold(self, usd: Decimal = Decimal(0), base: Decimal = Decimal(0)) -> None:
        if usd > self.available_usd:
            raise InsufficientBalance(f"insufficient USD: need {usd:.2f}, available {self.available_usd:.2f}")
        if base > self.available_base:
            raise InsufficientBalance(f"insufficient BTC: need {base}, available {self.available_base}")
        self.held_usd += usd
        self.held_base += base

    def release(self, usd: Decimal = Decimal(0), base: Decimal = Decimal(0)) -> None:
        self.held_usd = max(Decimal(0), self.held_usd - usd)
        self.held_base = max(Decimal(0), self.held_base - base)

    def equity(self, mark: Decimal) -> Decimal:
        return self.usd + self.base * mark

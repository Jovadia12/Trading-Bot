"""Coinbase maker/taker fee handling for paper fills.

Preferred source: the account's own rates from ``GET /api/v3/brokerage/transaction_summary``
(``fee_tier.maker_fee_rate`` / ``taker_fee_rate``). Fallback: a configured default that is
explicitly labelled UNCONFIRMED (see VENUE_EXECUTION_RESEARCH.md). Fees are charged in the
quote currency (USD) on each fill's notional.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from execution.models import Liquidity


@dataclass(frozen=True)
class FeeSchedule:
    maker_rate: Decimal
    taker_rate: Decimal
    source: str

    def rate(self, liquidity: Liquidity) -> Decimal:
        return self.maker_rate if liquidity is Liquidity.MAKER else self.taker_rate

    def fee(self, notional: Decimal, liquidity: Liquidity) -> Decimal:
        return notional * self.rate(liquidity)

    @classmethod
    def from_account(cls, rates: dict) -> "FeeSchedule":
        return cls(Decimal(str(rates["maker_fee_rate"])), Decimal(str(rates["taker_fee_rate"])),
                   f"account /transaction_summary (tier: {rates.get('pricing_tier')})")


DEFAULT_US_ENTRY_TIER = FeeSchedule(
    Decimal("0.0050"), Decimal("0.0090"),
    "DEFAULT, UNCONFIRMED: Coinbase Advanced US entry tier 0.50% maker / 0.90% taker "
    "(third-party summaries; see VENUE_EXECUTION_RESEARCH.md). Replace with account rates.",
)

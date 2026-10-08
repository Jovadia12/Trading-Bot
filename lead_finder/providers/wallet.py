"""Wallet data provider abstraction.

The lead pipeline only depends on this interface, so a different blockchain
intelligence provider can be added without touching the lead system. Nansen is
the implementation shipped here (``providers/nansen.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class DiscoveredWallet:
    chain: str
    address: str
    source: str                      # e.g. "Nansen tgm/who-bought-sold WETH (30d)"
    provider_label: str | None = None
    volume_usd: float | None = None


@dataclass
class TokenHolding:
    symbol: str | None
    token_address: str | None
    amount: float | None
    price_usd: float | None
    value_usd: float | None          # None = provider could not price it


@dataclass
class Holdings:
    chain: str
    address: str
    tokens: list[TokenHolding]
    estimated_value_usd: float | None   # None = unknown. Never coerced to 0.
    holdings_status: str                # "Known" | "Partial" | "Holdings unavailable"
    native_balance: float | None
    native_symbol: str
    asset_count: int
    debt_positions: list[str] = field(default_factory=list)


@dataclass
class Activity:
    chain: str
    address: str
    trade_count: int | None             # None = unknown
    truncated: bool                     # True when more trades exist than were fetched
    last_active_at: str | None
    window_days: int
    recent: list[dict] = field(default_factory=list)
    source: str = ""


@dataclass
class ProviderLabel:
    label: str
    category: str | None = None


class WalletDataProvider(Protocol):
    name: str

    @property
    def configured(self) -> bool: ...

    def supported_chains(self) -> list[str]: ...

    def discover(self, chain: str, token_address: str, days: int, limit: int) -> list[DiscoveredWallet]: ...

    def holdings(self, chain: str, address: str) -> Holdings: ...

    def activity(self, chain: str, address: str, days: int) -> Activity: ...

    def labels(self, chain: str, address: str) -> list[ProviderLabel]: ...

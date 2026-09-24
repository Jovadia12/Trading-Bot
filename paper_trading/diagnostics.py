"""Startup diagnostic: authenticated read-only checks. Prints ONLY status lines, never
credentials, balances, tokens or raw API responses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from exchange.client import ExchangeClient
from exchange.errors import ExchangeAPIError
from execution.fees import FeeSchedule
from market_data.models import ProductSpec


def _ok(flag: Optional[bool]) -> str:
    return "SUCCESS" if flag else "FAIL"


@dataclass
class Diagnostics:
    credentials_loaded: bool = False
    authenticated: bool = False
    product: bool = False
    market_data: bool = False
    account: bool = False
    fees: bool = False
    # details kept for the run summary (never secrets)
    product_spec: Optional[ProductSpec] = None
    fee_schedule: Optional[FeeSchedule] = None
    pricing_tier: Optional[str] = None
    accounts: Optional[list] = None
    permissions: Optional[dict] = None
    errors: dict = field(default_factory=dict)   # check -> short sanitized reason

    def lines(self) -> list[str]:
        return [
            f"API credentials loaded: {'YES' if self.credentials_loaded else 'NO'}",
            f"Authenticated Coinbase connection: {_ok(self.authenticated)}",
            f"BTC/USD product: {_ok(self.product)}",
            f"Market data stream: {_ok(self.market_data)}",
            f"Account data: {_ok(self.account)}",
            f"Fee data: {_ok(self.fees)}",
            "PAPER MODE: ENABLED",
        ]


def _reason(exc: Exception) -> str:
    status = getattr(exc, "status", None)
    return f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")


def run_rest_checks(client: ExchangeClient, credentials_loaded: bool, product_id: str = "BTC-USD",
                    offline: bool = False) -> Diagnostics:
    """Authenticated read-only checks. Any failure is recorded, never raised."""
    d = Diagnostics(credentials_loaded=credentials_loaded)
    if offline:
        d.errors["all"] = "offline replay: REST checks skipped"
        return d
    if credentials_loaded:
        try:
            d.permissions = client.get_key_permissions()
            d.authenticated = True
        except (ExchangeAPIError, KeyError, ValueError) as exc:
            d.errors["authentication"] = _reason(exc)
    else:
        d.errors["authentication"] = "no credentials in environment"
    try:
        d.product_spec = client.get_product(product_id)   # authenticated if creds work, else public
        d.product = d.product_spec.product_id == product_id
    except (ExchangeAPIError, KeyError, ValueError) as exc:
        d.errors["product"] = _reason(exc)
    if d.authenticated:
        try:
            d.accounts = client.get_accounts()
            d.account = True
        except (ExchangeAPIError, KeyError, ValueError) as exc:
            d.errors["account"] = _reason(exc)
        try:
            rates = client.get_fee_rates()
            d.fee_schedule = FeeSchedule.from_account(rates)
            d.pricing_tier = rates.get("pricing_tier")
            d.fees = True
        except (ExchangeAPIError, KeyError, ValueError, TypeError) as exc:
            d.errors["fees"] = _reason(exc)
    return d

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_data.models import MarketTrade, ProductSpec
from market_data.order_book import L2OrderBook

T0 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _paper_mode_and_no_creds(monkeypatch):
    monkeypatch.setenv("PAPER_MODE", "true")
    for k in ("COINBASE_API_KEY", "COINBASE_API_SECRET", "ALLOW_TRADE_SCOPED_KEY"):
        monkeypatch.delenv(k, raising=False)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


@pytest.fixture
def product():
    return ProductSpec("BTC-USD", "BTC", "USD", Decimal("0.00000001"), Decimal("0.01"), Decimal("0.01"),
                       Decimal("0.00001"), Decimal("3400"), Decimal("1"))


def make_book(bids, asks) -> L2OrderBook:
    b = L2OrderBook("BTC-USD")
    b.load_levels([(Decimal(str(p)), Decimal(str(s))) for p, s in bids],
                  [(Decimal(str(p)), Decimal(str(s))) for p, s in asks], T0)
    return b


def trade(price, size, t) -> MarketTrade:
    return MarketTrade("BTC-USD", t, Decimal(str(price)), Decimal(str(size)), "SELL")

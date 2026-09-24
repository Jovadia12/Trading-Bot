"""Exchange client interface and the read-only Coinbase Advanced implementation.

``ExchangeClient`` exposes market/account *reads* only. Every method that would act on a
real order or move funds exists solely to raise ``LiveOrderExecutionDisabled``. There is no
LiveExecutionEngine in this project.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from config.settings import Credentials, require_paper_mode
from exchange.endpoints import API_PREFIX
from exchange.errors import ExchangeAPIError, LiveOrderExecutionDisabled
from exchange.transport import ReadOnlyTransport
from market_data.models import D, Candle, MarketTrade, ProductSpec, Quote, parse_time

log = logging.getLogger(__name__)

GRANULARITIES = {
    "1m": "ONE_MINUTE", "5m": "FIVE_MINUTE", "15m": "FIFTEEN_MINUTE", "30m": "THIRTY_MINUTE",
    "1h": "ONE_HOUR", "2h": "TWO_HOUR", "4h": "FOUR_HOUR", "6h": "SIX_HOUR", "1d": "ONE_DAY",
}
MAX_CANDLES_PER_REQUEST = 350  # Coinbase limit per candles request


class ExchangeClient(ABC):
    """Read-only exchange interface. Order/fund methods are hard-disabled."""

    # ---- reads -----------------------------------------------------------------------------
    @abstractmethod
    def get_product(self, product_id: str) -> ProductSpec: ...

    @abstractmethod
    def get_best_bid_ask(self, product_id: str) -> Quote: ...

    @abstractmethod
    def get_order_book(self, product_id: str, limit: int = 50) -> dict: ...

    @abstractmethod
    def get_candles(self, product_id: str, start: datetime, end: datetime, granularity: str) -> list[Candle]: ...

    @abstractmethod
    def get_market_trades(self, product_id: str, limit: int = 100) -> list[MarketTrade]: ...

    @abstractmethod
    def get_accounts(self) -> list[dict]: ...

    @abstractmethod
    def get_portfolios(self) -> list[dict]: ...

    @abstractmethod
    def get_fee_rates(self) -> dict: ...

    @abstractmethod
    def get_key_permissions(self) -> dict: ...

    # ---- permanently disabled --------------------------------------------------------------
    def place_order(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("place_order")

    def create_order(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("create_order")

    def market_order(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("market_order")

    def limit_order(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("limit_order")

    def preview_order(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("preview_order")

    def edit_order(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("edit_order")

    def cancel_order(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("cancel_order")

    def cancel_orders(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("cancel_orders")

    def close_position(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("close_position")

    def move_portfolio_funds(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("move_portfolio_funds")

    def withdraw(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("withdraw")

    def deposit(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("deposit")

    def convert(self, *args, **kwargs):
        raise LiveOrderExecutionDisabled("convert")


DISABLED_METHODS = (
    "place_order", "create_order", "market_order", "limit_order", "preview_order", "edit_order",
    "cancel_order", "cancel_orders", "close_position", "move_portfolio_funds", "withdraw",
    "deposit", "convert",
)


class CoinbaseAdvancedClient(ExchangeClient):
    """Coinbase Advanced Trade REST, read-only. Public endpoints are used when no credentials."""

    def __init__(self, credentials: Optional[Credentials] = None, transport: Optional[ReadOnlyTransport] = None):
        require_paper_mode()
        self._transport = transport or ReadOnlyTransport(credentials)
        self._auth = self._transport.authenticated

    def __getattr__(self, name):
        # Any unknown attribute that looks like a trading/funding action is refused explicitly.
        lowered = name.lower()
        if any(w in lowered for w in ("order", "withdraw", "transfer", "send", "buy", "sell", "trade_", "fund")):
            raise LiveOrderExecutionDisabled(name)
        raise AttributeError(name)

    def _get(self, path: str, params: Optional[dict] = None):
        return self._transport.request("GET", f"{API_PREFIX}{path}", params)

    # ---- products / market data --------------------------------------------------------
    def get_product(self, product_id: str = "BTC-USD") -> ProductSpec:
        if self._auth:
            try:
                return ProductSpec.from_api(self._get(f"/products/{product_id}"))
            except ExchangeAPIError as exc:
                if exc.status not in (401, 403) and exc.status is not None:
                    raise
                log.warning("authenticated product read failed; using public endpoint")
        return ProductSpec.from_api(self._get(f"/market/products/{product_id}"))

    def get_order_book(self, product_id: str = "BTC-USD", limit: int = 50) -> dict:
        path = "/product_book" if self._auth else "/market/product_book"
        data = self._get(path, {"product_id": product_id, "limit": limit})
        book = data.get("pricebook", data)
        return {
            "product_id": book.get("product_id", product_id),
            "time": parse_time(book["time"]) if book.get("time") else datetime.now(timezone.utc),
            "bids": [(D(l["price"]), D(l["size"])) for l in book.get("bids", [])],
            "asks": [(D(l["price"]), D(l["size"])) for l in book.get("asks", [])],
        }

    def get_best_bid_ask(self, product_id: str = "BTC-USD") -> Quote:
        if self._auth:
            data = self._get("/best_bid_ask", {"product_ids": product_id})
            books = data.get("pricebooks", [])
            if not books:
                raise ExchangeAPIError("best_bid_ask returned no pricebooks")
            b = books[0]
            return Quote(product_id, parse_time(b["time"]), D(b["bids"][0]["price"]), D(b["bids"][0]["size"]),
                         D(b["asks"][0]["price"]), D(b["asks"][0]["size"]))
        book = self.get_order_book(product_id, limit=1)
        (bp, bs), (ap, as_) = book["bids"][0], book["asks"][0]
        return Quote(product_id, book["time"], bp, bs, ap, as_)

    def get_candles(self, product_id: str, start: datetime, end: datetime, granularity: str = "1m") -> list[Candle]:
        gran = GRANULARITIES.get(granularity, granularity)
        path = f"/products/{product_id}/candles" if self._auth else f"/market/products/{product_id}/candles"
        data = self._get(path, {"start": str(int(start.timestamp())), "end": str(int(end.timestamp())),
                                "granularity": gran})
        out = [Candle(parse_time(c["start"]), D(c["open"]), D(c["high"]), D(c["low"]), D(c["close"]), D(c["volume"]))
               for c in data.get("candles", [])]
        return sorted(out, key=lambda c: c.start)

    def get_market_trades(self, product_id: str = "BTC-USD", limit: int = 100) -> list[MarketTrade]:
        path = f"/products/{product_id}/ticker" if self._auth else f"/market/products/{product_id}/ticker"
        data = self._get(path, {"limit": limit})
        return [MarketTrade(t.get("product_id", product_id), parse_time(t["time"]), D(t["price"]), D(t["size"]),
                            str(t.get("side", "")), t.get("trade_id")) for t in data.get("trades", [])]

    # ---- account (auth, read-only) -----------------------------------------------------
    def get_accounts(self) -> list[dict]:
        accounts, cursor = [], None
        while True:
            data = self._get("/accounts", {"limit": 250, "cursor": cursor})
            accounts.extend(data.get("accounts", []))
            if not data.get("has_next"):
                return accounts
            cursor = data.get("cursor")

    def get_portfolios(self) -> list[dict]:
        return self._get("/portfolios").get("portfolios", [])

    def get_fee_rates(self) -> dict:
        """Account's current maker/taker rates from /transaction_summary (read-only)."""
        data = self._get("/transaction_summary")
        tier = data.get("fee_tier", {})
        return {
            "maker_fee_rate": D(tier["maker_fee_rate"]),
            "taker_fee_rate": D(tier["taker_fee_rate"]),
            "pricing_tier": tier.get("pricing_tier"),
            "total_volume": data.get("total_volume"),
        }

    def get_key_permissions(self) -> dict:
        return self._get("/key_permissions")


def summarize_balances(accounts: Iterable[dict], currencies=("USD", "BTC")) -> dict[str, Decimal]:
    out = {c: Decimal(0) for c in currencies}
    for a in accounts:
        cur = a.get("currency")
        if cur in out:
            out[cur] += D(a.get("available_balance", {}).get("value", "0"))
    return out

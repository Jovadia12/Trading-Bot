"""Coinbase Advanced Trade endpoint policy.

Only the GET endpoints below can ever be requested. Everything else -- in particular every
order, portfolio-mutation, conversion, and payment endpoint -- is rejected by the transport
before any network I/O happens. The blocklist is kept for documentation and tests; the
allowlist is what is actually enforced (deny by default).
"""
from __future__ import annotations

import re

API_HOST = "api.coinbase.com"
API_PREFIX = "/api/v3/brokerage"
WS_MARKET_DATA_URL = "wss://advanced-trade-ws.coinbase.com"

# (path regex, requires_auth). Anchored, GET only.
_PID = r"[A-Z0-9]{2,10}-[A-Z0-9]{2,10}"
READ_ONLY_ENDPOINTS: tuple[tuple[re.Pattern, bool], ...] = tuple(
    (re.compile(p), auth)
    for p, auth in (
        # public (no auth)
        (rf"^{API_PREFIX}/time$", False),
        (rf"^{API_PREFIX}/market/products/{_PID}$", False),
        (rf"^{API_PREFIX}/market/product_book$", False),
        (rf"^{API_PREFIX}/market/products/{_PID}/candles$", False),
        (rf"^{API_PREFIX}/market/products/{_PID}/ticker$", False),
        # authenticated, read-only
        (rf"^{API_PREFIX}/accounts$", True),
        (rf"^{API_PREFIX}/accounts/[0-9a-fA-F\-]{{36}}$", True),
        (rf"^{API_PREFIX}/portfolios$", True),
        (rf"^{API_PREFIX}/portfolios/[0-9a-fA-F\-]{{36}}$", True),
        (rf"^{API_PREFIX}/products/{_PID}$", True),
        (rf"^{API_PREFIX}/product_book$", True),
        (rf"^{API_PREFIX}/best_bid_ask$", True),
        (rf"^{API_PREFIX}/products/{_PID}/candles$", True),
        (rf"^{API_PREFIX}/products/{_PID}/ticker$", True),
        (rf"^{API_PREFIX}/transaction_summary$", True),
        (rf"^{API_PREFIX}/key_permissions$", True),
    )
)

# Never reachable. Listed so tests can assert each one is refused.
FORBIDDEN_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("POST", f"{API_PREFIX}/orders"),
    ("POST", f"{API_PREFIX}/orders/preview"),
    ("POST", f"{API_PREFIX}/orders/edit"),
    ("POST", f"{API_PREFIX}/orders/edit_preview"),
    ("POST", f"{API_PREFIX}/orders/batch_cancel"),
    ("POST", f"{API_PREFIX}/orders/close_position"),
    ("POST", f"{API_PREFIX}/convert/quote"),
    ("POST", f"{API_PREFIX}/convert/trade/abc"),
    ("POST", f"{API_PREFIX}/portfolios"),
    ("POST", f"{API_PREFIX}/portfolios/move_funds"),
    ("PUT", f"{API_PREFIX}/portfolios/00000000-0000-0000-0000-000000000000"),
    ("DELETE", f"{API_PREFIX}/portfolios/00000000-0000-0000-0000-000000000000"),
    ("GET", f"{API_PREFIX}/orders/historical/batch"),   # not needed; deny by default
    ("GET", f"{API_PREFIX}/orders/historical/fills"),
    ("POST", "/v2/accounts/abc/transactions"),          # legacy send/withdraw
    ("POST", "/v2/accounts/abc/withdrawals"),
    ("POST", "/v2/accounts/abc/deposits"),
    ("GET", f"{API_PREFIX}/orders"),                    # wrong method + not allowlisted
)


def match_read_only(method: str, path: str) -> tuple[bool, bool]:
    """Return (allowed, requires_auth) for a method/path pair."""
    if method.upper() != "GET":
        return False, False
    for pattern, auth in READ_ONLY_ENDPOINTS:
        if pattern.match(path):
            return True, auth
    return False, False

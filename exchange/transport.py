"""HTTP transport that can only issue allowlisted, read-only GET requests.

This is the single choke point for all network calls to Coinbase REST. It enforces
deny-by-default *before* building auth headers or touching the network, so an order
endpoint cannot be reached even by constructing a request manually.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from config.settings import Credentials
from exchange.auth import build_jwt, format_jwt_uri
from exchange.endpoints import API_HOST, match_read_only
from exchange.errors import ExchangeAPIError, ForbiddenEndpointError

log = logging.getLogger(__name__)


class ReadOnlyTransport:
    def __init__(self, credentials: Optional[Credentials] = None, session: Optional[requests.Session] = None,
                 timeout: float = 10.0):
        self._credentials = credentials
        self._session = session or requests.Session()
        self._timeout = timeout

    @property
    def authenticated(self) -> bool:
        return self._credentials is not None

    def request(self, method: str, path: str, params: Optional[dict] = None) -> Any:
        allowed, requires_auth = match_read_only(method, path)
        if not allowed:
            raise ForbiddenEndpointError(f"{method.upper()} {path} is not a permitted read-only endpoint")
        headers = {"Accept": "application/json"}
        if requires_auth:
            if not self._credentials:
                raise ExchangeAPIError(f"{path} requires COINBASE_API_KEY/COINBASE_API_SECRET")
            token = build_jwt(self._credentials.api_key, self._credentials.api_secret,
                              uri=format_jwt_uri("GET", path))
            headers["Authorization"] = f"Bearer {token}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"https://{API_HOST}{path}"
        try:
            resp = self._session.get(url, params=clean, headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            raise ExchangeAPIError(f"GET {path} failed: {type(exc).__name__}: {exc}") from exc
        if resp.status_code != 200:
            # body can contain request echoes but never our secret; still truncate
            raise ExchangeAPIError(f"GET {path} -> HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ExchangeAPIError(f"GET {path} returned non-JSON") from exc

    # Explicitly refuse any write verb even if someone calls it directly.
    def post(self, *_a, **_k):
        raise ForbiddenEndpointError("POST is never permitted")

    put = delete = patch = post

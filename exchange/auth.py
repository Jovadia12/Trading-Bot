"""JWT authentication for Coinbase Advanced Trade, delegated to Coinbase's official SDK.

The secret is first normalized by ``exchange.credentials.inspect_secret`` (repairs formatting
damage, validates the key cryptographically, converts to the canonical CDP representation), then
``coinbase.jwt_generator`` from the official ``coinbase-advanced-py`` package signs the token
(EdDSA for Ed25519, ES256 for legacy EC). The SDK's REST/WebSocket clients -- which contain order
functions -- are never imported anywhere in this project (a test enforces that).
"""
from __future__ import annotations

from functools import lru_cache

from coinbase import jwt_generator as _official

from exchange.credentials import CredentialFormatError, inspect_secret
from exchange.endpoints import API_HOST

__all__ = ["CredentialFormatError", "build_jwt", "format_jwt_uri"]


def format_jwt_uri(method: str, path: str) -> str:
    uri = _official.format_jwt_uri(method.upper(), path)
    assert uri == f"{method.upper()} {API_HOST}{path}"
    return uri


@lru_cache(maxsize=4)
def _canonical_secret(api_secret: str) -> str:
    return inspect_secret(api_secret).canonical


def build_jwt(api_key: str, api_secret: str, uri: str | None = None) -> str:
    """REST JWT when ``uri`` is given, otherwise a WebSocket JWT (both signed by the official SDK)."""
    secret = _canonical_secret(api_secret)          # raises CredentialFormatError (shape-only message)
    try:
        if uri:
            return _official.build_rest_jwt(uri, api_key, secret)
        return _official.build_ws_jwt(api_key, secret)
    except Exception:  # never chain SDK exceptions (defence in depth against echoing inputs)
        raise CredentialFormatError("official SDK could not sign a JWT with the normalized secret") from None

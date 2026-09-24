"""JWT authentication for Coinbase Advanced Trade, delegated to Coinbase's official SDK.

Only ``coinbase.jwt_generator`` from the official ``coinbase-advanced-py`` package is used.
Its REST/WebSocket clients (which contain order functions) are never imported anywhere in
this project -- a test enforces that. The official generator handles Ed25519 (EdDSA) and
legacy EC (ES256) CDP keys: claims ``sub, iss="cdp", nbf, exp=nbf+120, uri``; headers
``kid, nonce``. Tokens are short-lived and never logged.
"""
from __future__ import annotations

from coinbase import jwt_generator as _official

from exchange.endpoints import API_HOST


class CredentialFormatError(ValueError):
    """The secret could not be loaded as a CDP key. The message never contains the secret."""


def format_jwt_uri(method: str, path: str) -> str:
    uri = _official.format_jwt_uri(method.upper(), path)
    assert uri == f"{method.upper()} {API_HOST}{path}"
    return uri


def build_jwt(api_key: str, api_secret: str, uri: str | None = None) -> str:
    """REST JWT when ``uri`` is given, otherwise a WebSocket JWT (both via the official SDK)."""
    try:
        if uri:
            return _official.build_rest_jwt(uri, api_key, api_secret)
        return _official.build_ws_jwt(api_key, api_secret)
    except Exception:  # official errors don't echo the secret, but never chain them to be safe
        raise CredentialFormatError(
            "COINBASE_API_SECRET could not be loaded as an Ed25519 (base64) or EC PEM private key"
        ) from None

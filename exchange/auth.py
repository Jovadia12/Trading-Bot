"""JWT construction for Coinbase Developer Platform (CDP) API keys.

Mirrors the official coinbase-advanced-py SDK (``coinbase/jwt_generator.py``): claims
``sub=<key name>, iss="cdp", nbf, exp=nbf+120, uri="<METHOD> api.coinbase.com<path>"`` and
headers ``kid=<key name>, nonce=<random hex>``. Ed25519 keys sign with EdDSA; legacy EC P-256
PEM keys sign with ES256. Tokens are short-lived and are never logged.
"""
from __future__ import annotations

import base64
import binascii
import secrets
import time
from typing import Optional

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from exchange.endpoints import API_HOST

JWT_TTL_SECONDS = 120


class CredentialFormatError(ValueError):
    """The secret is neither a PEM private key nor a base64 Ed25519 key. Never includes the value."""


def load_private_key(secret: str):
    if secret.lstrip().startswith("-----BEGIN"):
        try:
            return serialization.load_pem_private_key(secret.encode("utf-8"), password=None)
        except (ValueError, TypeError) as exc:
            raise CredentialFormatError("PEM private key could not be parsed") from exc
    try:
        raw = base64.b64decode("".join(secret.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CredentialFormatError("secret is neither PEM nor valid base64") from exc
    if len(raw) not in (32, 64):
        raise CredentialFormatError(f"Ed25519 key must decode to 32 or 64 bytes (got {len(raw)})")
    return ed25519.Ed25519PrivateKey.from_private_bytes(raw[:32])


def algorithm_for(private_key) -> str:
    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        return "EdDSA"
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        return "ES256"
    raise CredentialFormatError(f"unsupported key type {type(private_key).__name__}")


def format_jwt_uri(method: str, path: str) -> str:
    return f"{method.upper()} {API_HOST}{path}"


def build_jwt(api_key: str, api_secret: str, uri: Optional[str] = None, now: Optional[int] = None) -> str:
    private_key = load_private_key(api_secret)
    ts = int(time.time()) if now is None else int(now)
    claims = {"sub": api_key, "iss": "cdp", "nbf": ts, "exp": ts + JWT_TTL_SECONDS}
    if uri:
        claims["uri"] = uri
    return jwt.encode(
        claims,
        private_key,
        algorithm=algorithm_for(private_key),
        headers={"kid": api_key, "nonce": secrets.token_hex()},
    )

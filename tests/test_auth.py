import ast
import base64
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

import exchange.auth as auth
from exchange.auth import CredentialFormatError, build_jwt, format_jwt_uri

KEY_NAME = "organizations/test-org/apiKeys/test-key"
REPO = Path(__file__).resolve().parent.parent


def cdp_style_ed25519_secret():
    """64-byte seed||public key, base64 -- the format the CDP portal downloads."""
    sk = ed25519.Ed25519PrivateKey.generate()
    seed = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(seed + pub).decode(), sk.public_key()


def test_ed25519_jwt_from_official_sdk_has_required_claims_and_headers():
    secret, pub = cdp_style_ed25519_secret()
    uri = format_jwt_uri("GET", "/api/v3/brokerage/accounts")
    assert uri == "GET api.coinbase.com/api/v3/brokerage/accounts"
    token = build_jwt(KEY_NAME, secret, uri=uri)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "EdDSA" and header["kid"] == KEY_NAME and len(header["nonce"]) >= 32
    claims = jwt.decode(token, pub, algorithms=["EdDSA"])
    assert claims["sub"] == KEY_NAME and claims["iss"] == "cdp" and claims["uri"] == uri
    assert claims["exp"] - claims["nbf"] == 120


def test_auth_delegates_to_official_coinbase_jwt_generator(monkeypatch):
    calls = []
    monkeypatch.setattr(auth._official, "build_rest_jwt", lambda uri, k, s: calls.append(uri) or "tok")
    assert build_jwt(KEY_NAME, "x", uri="GET api.coinbase.com/p") == "tok" and calls == ["GET api.coinbase.com/p"]
    assert auth._official.__name__ == "coinbase.jwt_generator"


def test_ed25519_32_byte_seed_also_accepted():
    sk = ed25519.Ed25519PrivateKey.generate()
    seed = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    jwt.decode(build_jwt(KEY_NAME, base64.b64encode(seed).decode(), uri="GET api.coinbase.com/x"),
               sk.public_key(), algorithms=["EdDSA"])


def test_legacy_ec_pem_uses_es256():
    sk = ec.generate_private_key(ec.SECP256R1())
    pem = sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                           serialization.NoEncryption()).decode()
    token = build_jwt(KEY_NAME, pem, uri="GET api.coinbase.com/x")
    assert jwt.get_unverified_header(token)["alg"] == "ES256"


@pytest.mark.parametrize("bad", ["not-a-key!!", base64.b64encode(b"x" * 10).decode(), ""])
def test_bad_secret_error_does_not_echo_secret(bad):
    with pytest.raises(CredentialFormatError) as exc:
        build_jwt(KEY_NAME, bad, uri="GET api.coinbase.com/x")
    assert (not bad or bad not in str(exc.value)) and exc.value.__cause__ is None


def test_sdk_order_capable_clients_are_never_imported():
    """Only coinbase.jwt_generator may be imported from the official SDK."""
    for path in REPO.rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            for m in mods:
                if m.startswith("coinbase"):
                    assert m in ("coinbase", "coinbase.jwt_generator"), (path, m)

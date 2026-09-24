import base64

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from exchange.auth import CredentialFormatError, build_jwt, format_jwt_uri

KEY_NAME = "organizations/test-org/apiKeys/test-key"


def cdp_style_ed25519_secret():
    """64-byte seed||public key, base64 -- the format the CDP portal downloads."""
    sk = ed25519.Ed25519PrivateKey.generate()
    seed = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(seed + pub).decode(), sk.public_key()


def test_ed25519_jwt_claims_and_headers():
    secret, pub = cdp_style_ed25519_secret()
    uri = format_jwt_uri("GET", "/api/v3/brokerage/accounts")
    token = build_jwt(KEY_NAME, secret, uri=uri, now=1_800_000_000)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "EdDSA" and header["kid"] == KEY_NAME and len(header["nonce"]) >= 32
    claims = jwt.decode(token, pub, algorithms=["EdDSA"], options={"verify_nbf": False, "verify_exp": False})
    assert claims == {"sub": KEY_NAME, "iss": "cdp", "nbf": 1_800_000_000, "exp": 1_800_000_120,
                      "uri": "GET api.coinbase.com/api/v3/brokerage/accounts"}


def test_ed25519_32_byte_seed_also_accepted():
    sk = ed25519.Ed25519PrivateKey.generate()
    seed = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    token = build_jwt(KEY_NAME, base64.b64encode(seed).decode())
    jwt.decode(token, sk.public_key(), algorithms=["EdDSA"])


def test_legacy_ec_pem_uses_es256():
    sk = ec.generate_private_key(ec.SECP256R1())
    pem = sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                           serialization.NoEncryption()).decode()
    token = build_jwt(KEY_NAME, pem)
    assert jwt.get_unverified_header(token)["alg"] == "ES256"
    jwt.decode(token, sk.public_key(), algorithms=["ES256"])


@pytest.mark.parametrize("bad", ["not-a-key!!", base64.b64encode(b"x" * 10).decode()])
def test_bad_secret_error_does_not_echo_secret(bad):
    with pytest.raises(CredentialFormatError) as exc:
        build_jwt(KEY_NAME, bad)
    assert bad not in str(exc.value)

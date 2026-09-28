"""The exact CDP credential formats, and the ways they get mangled on the way into .env.

All keys here are generated on the fly; no real credential is used or stored.
"""
import base64
import json
import logging

import jwt
import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

import config.settings as cs
from config.settings import EnvFileError, env_file_conflicts, load_settings, parse_env_file
from exchange.auth import build_jwt
from exchange.credentials import CredentialFormatError, describe_key_name, inspect_secret, normalize_key_name

KEY = "organizations/94c647b9-0000-4e4f-b86e-000000000000/apiKeys/4daad28b-0000-4a78-b101-000000000000"
URI = "GET api.coinbase.com/api/v3/brokerage/key_permissions"


def new_key():
    sk = ed25519.Ed25519PrivateKey.generate()
    seed = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return sk, base64.b64encode(seed + pub).decode()   # exactly what the CDP portal shows: 88 chars, ends with "=="


def verifies(secret, pub, key=KEY):
    token = build_jwt(key, secret, uri=URI)
    claims = jwt.decode(token, pub, algorithms=["EdDSA"])
    return claims["sub"] == key and claims["uri"] == URI


def test_cdp_portal_format_is_88_char_base64_of_64_bytes():
    _sk, secret = new_key()
    assert len(secret) == 88 and secret.endswith("==")
    info = inspect_secret(secret)
    assert info.algorithm == "EdDSA" and info.public_key_verified and info.fixes == []
    assert info.canonical == secret


MANGLINGS = {
    "double quotes": lambda s: f'"{s}"',
    "single quotes": lambda s: f"'{s}'",
    "macOS smart quotes": lambda s: f"“{s}”",
    "unmatched leading quote": lambda s: f'"{s}',
    "trailing newline/CRLF": lambda s: s + "\r\n",
    "literal \\n suffix": lambda s: s + "\\n",
    "inline comment": lambda s: s + "   # my coinbase key",
    "RTF trailing backslash": lambda s: s + "\\",
    "leading/trailing spaces": lambda s: f"   {s}   ",
    "missing padding": lambda s: s.rstrip("="),
    "url-safe alphabet": lambda s: s.replace("+", "-").replace("/", "_"),
    "wrapped over lines": lambda s: s[:40] + "\n" + s[40:],
    "zero-width space": lambda s: s[:10] + "​" + s[10:],
    "BOM": lambda s: "﻿" + s,
    "export prefix": lambda s: f"export {s}",
}


@pytest.mark.parametrize("name", MANGLINGS)
def test_mangled_cdp_secret_is_repaired_and_signs(name):
    sk, secret = new_key()
    value = MANGLINGS[name](secret)
    info = inspect_secret(value)
    assert info.canonical == secret, name
    assert verifies(value, sk.public_key())


def test_32_byte_seed_and_pkcs8_pem_and_der_forms():
    sk, secret = new_key()
    seed = base64.b64decode(secret)[:32]
    pem = sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()
    der = base64.b64encode(sk.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption())).decode()
    for v in (base64.b64encode(seed).decode(), pem, pem.replace("\n", "\\n"), " ".join(pem.split("\n")), der):
        assert inspect_secret(v).canonical == secret
        assert verifies(v, sk.public_key())


def test_json_key_file_content_and_key_file_env(tmp_path, monkeypatch):
    sk, secret = new_key()
    blob = json.dumps({"id": "4daad28b-0000-4a78-b101-000000000000", "privateKey": secret})
    info = inspect_secret(blob)
    assert info.canonical == secret and info.key_name_from_json.startswith("4daad28b")
    f = tmp_path / "cdp_api_key.json"
    f.write_text(json.dumps({"name": KEY, "privateKey": secret}))
    monkeypatch.setenv("COINBASE_API_KEY_FILE", str(f))
    s = load_settings()
    assert s.credentials.api_key == KEY and verifies(s.credentials.api_secret, sk.public_key())


def test_legacy_ec_pem_with_literal_newlines():
    k = ec.generate_private_key(ec.SECP256R1())
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                          serialization.NoEncryption()).decode()
    info = inspect_secret(pem.replace("\n", "\\n"))
    assert info.algorithm == "ES256"
    jwt.decode(build_jwt(KEY, pem.replace("\n", "\\n"), uri=URI), k.public_key(), algorithms=["ES256"])


@pytest.mark.parametrize("bad,expect", [
    ("", "empty"),
    ("abc!!def", "not base64"),
    (base64.b64encode(b"x" * 40).decode(), "40 bytes"),
    ("-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEI", "no matching END"),
])
def test_invalid_secrets_fail_with_shape_only_messages(bad, expect):
    with pytest.raises(CredentialFormatError) as exc:
        inspect_secret(bad)
    assert expect in str(exc.value)
    assert not bad or bad not in str(exc.value)


def test_64_bytes_with_wrong_public_half_is_rejected():
    _sk, secret = new_key()
    raw = bytearray(base64.b64decode(secret))
    raw[40] ^= 0xFF
    with pytest.raises(CredentialFormatError, match="not the matching Ed25519 public key"):
        inspect_secret(base64.b64encode(bytes(raw)).decode())


def test_key_name_normalization_and_description():
    for v in (KEY, f'"{KEY}"', f"{KEY}  # comment", f"“{KEY}”\\", f" {KEY}\\n"):
        name, _ = normalize_key_name(v)
        assert name == KEY
    assert describe_key_name(KEY) == "organizations/<uuid>/apiKeys/<uuid>"
    assert describe_key_name("4daad28b-0000-4a78-b101-000000000000") == "<uuid> (CDP key id)"
    assert describe_key_name("my key").startswith("UNRECOGNIZED")


# ---- .env file handling ------------------------------------------------------------------------

def test_env_file_variants_load_and_sign(tmp_path, monkeypatch):
    sk, secret = new_key()
    pem = sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()
    env = tmp_path / ".env"
    env.write_text(
        "# Coinbase\n"
        f"export COINBASE_API_KEY=\"{KEY}\"\n"
        f"COINBASE_API_SECRET=\"{pem}\"\n"          # multi-line quoted PEM
        "PAPER_MODE=true\n")
    vals = parse_env_file(env)
    assert vals["COINBASE_API_KEY"] == KEY and "END PRIVATE KEY" in vals["COINBASE_API_SECRET"]
    monkeypatch.delenv("PAPER_MODE")
    s = load_settings(env)
    assert verifies(s.credentials.api_secret, sk.public_key())


def test_rich_text_env_file_is_rejected_with_clear_message(tmp_path):
    env = tmp_path / ".env"
    env.write_text("{\\rtf1\\ansi\\ansicpg1252\\cocoartf2761\n\\f0\\fs24 COINBASE_API_KEY=x\\\nPAPER_MODE=true}")
    with pytest.raises(EnvFileError, match="Rich Text") as exc:
        parse_env_file(env)
    assert "COINBASE_API_KEY=x" not in str(exc.value)


def test_shell_env_conflict_reports_names_only(tmp_path):
    env = tmp_path / ".env"
    env.write_text("COINBASE_API_SECRET=fromfile\nPAPER_MODE=true\n")
    assert env_file_conflicts(env, shell_env={"COINBASE_API_SECRET": "stale", "PAPER_MODE": "true"}) == \
        ["COINBASE_API_SECRET"]


# ---- the connectivity check command ------------------------------------------------------------

class _Resp:
    def __init__(self, code, payload):
        self.status_code, self._p, self.text = code, payload, "{}"

    def json(self):
        return self._p


def _fake_coinbase(auth_ok):
    calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        path = url.replace("https://api.coinbase.com", "")
        calls.append((path, bool(headers and "Authorization" in headers)))
        if path.endswith("/time"):
            import time
            return _Resp(200, {"epochSeconds": str(int(time.time()))})
        if not auth_ok:
            return _Resp(401, {"error": "Unauthorized"})
        if path.endswith("/key_permissions"):
            return _Resp(200, {"can_view": True, "can_trade": False, "can_transfer": False})
        if path.endswith("/accounts"):
            return _Resp(200, {"accounts": [{"currency": "USD"}, {"currency": "BTC"}], "has_next": False})
        return _Resp(404, {})
    return get, calls


@pytest.mark.parametrize("auth_ok", [True, False])
def test_check_auth_command(monkeypatch, capsys, caplog, auth_ok):
    caplog.set_level(logging.DEBUG)
    sk, secret = new_key()
    monkeypatch.setenv("COINBASE_API_KEY", f'"{KEY}"')
    monkeypatch.setenv("COINBASE_API_SECRET", f"“{secret}”")    # smart-quoted, as TextEdit would
    get, calls = _fake_coinbase(auth_ok)
    monkeypatch.setattr(requests.Session, "get", get)
    from exchange.check_auth import main
    rc = main([])
    out = capsys.readouterr().out
    assert "Ed25519 raw base64 (64 bytes" in out and "repaired: secret: removed surrounding quotes" in out
    assert "Order endpoints called: NO" in out
    if auth_ok:
        assert rc == 0 and "AUTHENTICATED COINBASE CONNECTIVITY OK" in out and "2 accounts" in out
    else:
        assert rc == 1 and "HTTP 401" in out and "check: API key name must be the full value" in out
    for blob in (out, caplog.text):
        assert secret not in blob and KEY not in blob
    assert [p for p, _a in calls] [:2] == ["/api/v3/brokerage/time", "/api/v3/brokerage/key_permissions"]
    assert all("/orders" not in p for p, _a in calls)


def test_check_auth_requires_paper_mode(monkeypatch, capsys):
    monkeypatch.setenv("PAPER_MODE", "false")
    from exchange.check_auth import main
    assert main([]) == 2

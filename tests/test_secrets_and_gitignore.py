import base64
import logging
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from config.logging_setup import SecretRedactingFilter, setup_logging
from config.settings import Credentials, load_env_file, load_settings
from exchange.auth import build_jwt

REPO = Path(__file__).resolve().parent.parent
FAKE_KEY = "organizations/fake-org/apiKeys/fake-key-id-1234"


def fake_secret():
    sk = ed25519.Ed25519PrivateKey.generate()
    seed = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(seed + pub).decode()


def test_credentials_repr_is_redacted():
    c = Credentials(FAKE_KEY, "SUPERSECRETVALUE")
    assert "SUPERSECRET" not in repr(c) and FAKE_KEY not in str(c) and "redacted" in repr(c)


def test_filter_redacts_secret_key_jwt_bearer_and_pem():
    secret = fake_secret()
    token = build_jwt(FAKE_KEY, secret)
    f = SecretRedactingFilter([FAKE_KEY, secret])
    rec = logging.LogRecord("x", logging.INFO, __file__, 1,
                            "key=%s secret=%s hdr=Bearer %s raw=%s pem=%s", (FAKE_KEY, secret, token, token,
                            "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"), None)
    f.filter(rec)
    out = rec.getMessage()
    for s in (FAKE_KEY, secret, token, "abc\n"):
        assert s not in out
    assert "<redacted" in out


def test_env_loader_returns_names_only(tmp_path, monkeypatch):
    secret = fake_secret()
    env = tmp_path / ".env"
    env.write_text(f"PAPER_MODE=true\nCOINBASE_API_KEY={FAKE_KEY}\nCOINBASE_API_SECRET=\"{secret}\"\n")
    names = load_env_file(env, override=True)
    assert set(names) == {"PAPER_MODE", "COINBASE_API_KEY", "COINBASE_API_SECRET"}
    s = load_settings(env)
    assert s.credentials.api_secret == secret and secret not in repr(s)


def test_full_session_output_and_logs_contain_no_secret(tmp_path, monkeypatch, capsys, caplog):
    secret = fake_secret()
    monkeypatch.setenv("COINBASE_API_KEY", FAKE_KEY)
    monkeypatch.setenv("COINBASE_API_SECRET", secret)
    caplog.set_level(logging.DEBUG)
    from paper_trading.runner import main
    rc = main(["--replay", "tests/fixtures/ws_btcusd_synthetic.jsonl", "--demo-roundtrip",
               "--records-dir", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    blobs = [captured.out, captured.err, caplog.text] + [p.read_text() for p in tmp_path.rglob("*") if p.is_file()]
    for blob in blobs:
        assert secret not in blob and FAKE_KEY not in blob


@pytest.mark.parametrize("path", [".env", ".env.local", ".env.production", "secrets/cb.json", "credentials/cb.json",
                                  "cdp_api_key.key", "private.pem", "paper_trading/records/x/trades.csv"])
def test_gitignore_excludes_credentials_and_records(path):
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=REPO)
    assert r.returncode == 0, f"{path} is NOT ignored by git"


def test_example_env_is_not_ignored_and_has_no_values():
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", "config/env.example"], cwd=REPO)
    assert r.returncode == 1
    text = (REPO / "config" / "env.example").read_text()
    assert "COINBASE_API_SECRET=\n" in text and "COINBASE_API_KEY=\n" in text

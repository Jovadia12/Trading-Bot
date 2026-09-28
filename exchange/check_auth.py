"""Authenticated Coinbase connectivity check (read-only; never prints credentials).

    python3 -m exchange.check_auth

Steps: PAPER_MODE gate -> locate credentials (shell / .env / key file) -> describe their *shape*
and repair formatting damage -> build a JWT with the official SDK -> public server-time check
(clock skew breaks JWTs) -> GET /key_permissions and GET /accounts through the read-only
transport. No order, preview, cancel or funds endpoint is reachable from here (or anywhere).
"""
from __future__ import annotations

import os
import sys
import time
from typing import Optional

from config.logging_setup import setup_logging
from config.settings import (API_KEY_ENV, API_KEY_FILE_ENV, API_SECRET_ENV, DEFAULT_ENV_FILE, _SHELL_ENV,
                             EnvFileError, PaperModeError, env_file_conflicts, load_settings, parse_env_file)
from exchange.credentials import CredentialFormatError, describe_key_name, inspect_secret, normalize_key_name
from exchange.errors import ExchangeAPIError
from exchange.transport import ReadOnlyTransport

HINTS_401 = [
    "API key name must be the full value shown by the CDP portal, e.g. organizations/<org-uuid>/apiKeys/<key-uuid>",
    "the key and secret must belong to the SAME key (re-download or re-create if unsure)",
    "the key may have been deleted/revoked, or its IP allowlist excludes this machine's public IP",
    "the key must be a CDP Secret API key with the Advanced Trade / Coinbase App 'View' permission",
    "your computer clock must be accurate (see clock check above)",
]


def _source(name: str) -> str:
    if name in _SHELL_ENV:
        return "shell environment"
    if name in os.environ:
        return ".env file"
    return "not set"


def main(argv: Optional[list[str]] = None) -> int:
    out = print
    try:
        settings = load_settings()
    except PaperModeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except EnvFileError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except CredentialFormatError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    setup_logging()
    out("PAPER MODE: ENABLED (read-only check; no orders can be placed)")
    out(f".env file: {'found' if DEFAULT_ENV_FILE.is_file() else 'not found'} ({DEFAULT_ENV_FILE})")
    for name in env_file_conflicts():
        if name in (API_KEY_ENV, API_SECRET_ENV, "PAPER_MODE"):
            out(f"WARNING: {name} is set in your SHELL and differs from .env -- the shell value is used. "
                f"Run 'unset {name}' (and remove it from ~/.zshrc) to use .env.")
    if os.environ.get(API_KEY_FILE_ENV):
        out(f"{API_KEY_FILE_ENV}: set")

    raw_key = os.environ.get(API_KEY_ENV, "")
    raw_secret = os.environ.get(API_SECRET_ENV, "")
    out(f"{API_KEY_ENV}: {'set' if raw_key.strip() else 'NOT SET'} (source: {_source(API_KEY_ENV)})")
    out(f"{API_SECRET_ENV}: {'set' if raw_secret.strip() else 'NOT SET'} (source: {_source(API_SECRET_ENV)})")
    if settings.credentials is None:
        out("RESULT: FAIL - credentials not found. Put both variables in .env (plain text) or set "
            f"{API_KEY_FILE_ENV} to the downloaded CDP key JSON.")
        return 1

    key_name, key_fixes = normalize_key_name(settings.credentials.api_key)
    out(f"API key name format: {describe_key_name(key_name)}")
    for f in key_fixes:
        out(f"  repaired: {f}")
    try:
        info = inspect_secret(settings.credentials.api_secret)
    except CredentialFormatError as exc:
        out(f"API secret format: INVALID - {exc}")
        out("RESULT: FAIL - fix the secret value in .env (copy it again from the CDP key download).")
        return 1
    out(f"API secret format: {info.kind}; signing algorithm {info.algorithm}")
    for f in info.fixes:
        out(f"  repaired: {f}")

    transport = ReadOnlyTransport(settings.credentials)
    try:
        server = transport.request("GET", "/api/v3/brokerage/time")
        skew = time.time() - float(server.get("epochSeconds") or server.get("epochMillis", 0) / 1000)
        out(f"Clock vs Coinbase server: {skew:+.1f} s " + ("(OK)" if abs(skew) < 30 else "(TOO LARGE - fix system clock)"))
    except (ExchangeAPIError, ValueError, TypeError) as exc:
        out(f"Clock check / public connectivity: FAIL ({type(exc).__name__}{_status(exc)})")

    ok = True
    try:
        perms = transport.request("GET", "/api/v3/brokerage/key_permissions")
        out("GET /api/v3/brokerage/key_permissions: HTTP 200 -> AUTHENTICATED")
        out(f"  permissions: view={perms.get('can_view')} trade={perms.get('can_trade')} "
            f"transfer={perms.get('can_transfer')}")
        if perms.get("can_transfer") or perms.get("can_trade"):
            out("  NOTE: this key can trade and/or transfer. A View-only key is recommended; the paper "
                "session refuses Transfer keys and refuses Trade keys unless ALLOW_TRADE_SCOPED_KEY=true.")
    except (ExchangeAPIError, CredentialFormatError) as exc:
        ok = False
        out(f"GET /api/v3/brokerage/key_permissions: FAIL ({type(exc).__name__}{_status(exc)})")
        if getattr(exc, "status", None) in (401, 403):
            for h in HINTS_401:
                out(f"  check: {h}")
    if ok:
        try:
            data = transport.request("GET", "/api/v3/brokerage/accounts", {"limit": 250})
            out(f"GET /api/v3/brokerage/accounts: HTTP 200 ({len(data.get('accounts', []))} accounts readable)")
        except ExchangeAPIError as exc:
            ok = False
            out(f"GET /api/v3/brokerage/accounts: FAIL ({type(exc).__name__}{_status(exc)})")
    out(f"Order endpoints called: {'YES' if transport.order_endpoint_called else 'NO'}")
    out("RESULT: " + ("AUTHENTICATED COINBASE CONNECTIVITY OK" if ok else "FAIL"))
    return 0 if ok else 1


def _status(exc: Exception) -> str:
    s = getattr(exc, "status", None)
    if s:
        return f", HTTP {s}"
    if isinstance(exc, ExchangeAPIError):
        return ", network error: could not reach api.coinbase.com (firewall/VPN/proxy/offline?)"
    return f": {exc}"


if __name__ == "__main__":
    sys.exit(main())

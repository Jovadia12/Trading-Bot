"""Configuration and the mandatory PAPER_MODE safety gate.

Credentials are read from environment variables (optionally populated from a local,
git-ignored ``.env`` file). Secret values are never printed, logged or repr'd.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PAPER_MODE_ENV = "PAPER_MODE"
API_KEY_ENV = "COINBASE_API_KEY"
API_SECRET_ENV = "COINBASE_API_SECRET"
ALLOW_TRADE_KEY_ENV = "ALLOW_TRADE_SCOPED_KEY"

REPO_ROOT = Path(__file__).resolve().parent.parent


class PaperModeError(RuntimeError):
    """Raised when the process is not explicitly in paper mode."""


def require_paper_mode() -> None:
    """Refuse to run unless PAPER_MODE is exactly 'true' (case-insensitive, trimmed).

    There is intentionally no other accepted value and no override: live mode does not exist.
    """
    value = os.environ.get(PAPER_MODE_ENV)
    if value is None or value.strip().lower() != "true":
        raise PaperModeError(
            f"Refusing to start: {PAPER_MODE_ENV} must be set to 'true'. "
            "This project is research/paper mode only; live trading is not implemented."
        )


@dataclass(frozen=True)
class Credentials:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)

    def __repr__(self) -> str:  # never expose values
        return "Credentials(api_key=<redacted>, api_secret=<redacted>)"

    __str__ = __repr__


@dataclass(frozen=True)
class Settings:
    paper_mode: bool
    credentials: Optional[Credentials]
    allow_trade_scoped_key: bool
    product_id: str = "BTC-USD"

    @property
    def has_credentials(self) -> bool:
        return self.credentials is not None


def _parse_env_value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        raw = raw[1:-1]
    # Allow PEM keys stored on one line with literal \n escapes.
    return raw.replace("\\n", "\n")


def load_env_file(path: Optional[Path] = None, override: bool = False) -> list[str]:
    """Load KEY=VALUE lines from a local .env file into os.environ.

    Returns only the variable *names* that were loaded (never values). Missing file -> [].
    """
    path = Path(path) if path else REPO_ROOT / ".env"
    if not path.is_file():
        return []
    loaded = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, _, value = line.partition("=")
        name = name.strip()
        if not name:
            continue
        if override or name not in os.environ:
            os.environ[name] = _parse_env_value(value)
            loaded.append(name)
    return loaded


def load_settings(env_file: Optional[Path] = None) -> Settings:
    """Load settings, enforcing the paper-mode gate first."""
    load_env_file(env_file)
    require_paper_mode()
    key = os.environ.get(API_KEY_ENV, "").strip()
    secret = os.environ.get(API_SECRET_ENV, "").strip()
    creds = Credentials(key, secret) if key and secret else None
    allow_trade = os.environ.get(ALLOW_TRADE_KEY_ENV, "false").strip().lower() == "true"
    return Settings(paper_mode=True, credentials=creds, allow_trade_scoped_key=allow_trade)

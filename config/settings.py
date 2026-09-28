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
API_KEY_FILE_ENV = "COINBASE_API_KEY_FILE"   # optional: path to the CDP key JSON (keep outside the repo)
ALLOW_TRADE_KEY_ENV = "ALLOW_TRADE_SCOPED_KEY"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = REPO_ROOT / ".env"   # tests point this elsewhere so they never read a developer .env


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


class EnvFileError(ValueError):
    """The .env file itself is unusable (e.g. saved as Rich Text). Never contains values."""


_QUOTE_CHARS = "\"'"


def _parse_env_value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in _QUOTE_CHARS:
        raw = raw[1:-1]
    # Allow PEM keys stored on one line with literal \n escapes.
    return raw.replace("\\n", "\n")


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Supports ``export``, comments, quotes and multi-line quoted values
    (e.g. a PEM pasted between double quotes). Raises EnvFileError for rich-text files."""
    text = path.read_text(encoding="utf-8-sig")
    if text.lstrip().startswith("{\\rtf"):
        raise EnvFileError(f"{path.name} was saved as Rich Text (TextEdit). Re-save it as plain text "
                           "(TextEdit: Format > Make Plain Text) or create it with a code editor/nano.")
    values: dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not name:
            continue
        q = value[:1]
        if q in _QUOTE_CHARS and (len(value) == 1 or not value.rstrip().endswith(q)):
            parts = [value]
            while i < len(lines):          # multi-line quoted value
                parts.append(lines[i])
                i += 1
                if lines[i - 1].rstrip().endswith(q):
                    break
            value = "\n".join(parts)
        values[name] = _parse_env_value(value)
    return values


def env_file_conflicts(path: Optional[Path] = None, shell_env: Optional[dict] = None) -> list[str]:
    """Names set BOTH in the shell environment and in .env with DIFFERENT values (names only)."""
    path = Path(path) if path else DEFAULT_ENV_FILE
    shell = _SHELL_ENV if shell_env is None else shell_env
    if not path.is_file():
        return []
    try:
        file_values = parse_env_file(path)
    except EnvFileError:
        return []
    return [k for k, v in file_values.items() if k in shell and shell[k] != v]


# Snapshot of the process environment before any .env loading, to detect shell/.env conflicts.
_SHELL_ENV = dict(os.environ)


def load_env_file(path: Optional[Path] = None, override: bool = False) -> list[str]:
    """Load a local .env into os.environ (existing shell variables win unless override=True).

    Returns only the variable *names* that were loaded (never values). Missing file -> [].
    """
    path = Path(path) if path else DEFAULT_ENV_FILE
    if not path.is_file():
        return []
    loaded = []
    for name, value in parse_env_file(path).items():
        if override or name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded


def load_settings(env_file: Optional[Path] = None) -> Settings:
    """Load settings, enforcing the paper-mode gate first."""
    load_env_file(env_file)
    require_paper_mode()
    from exchange.credentials import load_key_file, normalize_key_name  # local import: no cycle at module load

    key = os.environ.get(API_KEY_ENV, "")
    secret = os.environ.get(API_SECRET_ENV, "")
    key_file = os.environ.get(API_KEY_FILE_ENV, "").strip()
    if key_file and not (key.strip() and secret.strip()):
        file_key, file_secret = load_key_file(key_file)
        key, secret = key or file_key, secret or file_secret
    key, _ = normalize_key_name(key)
    creds = Credentials(key, secret) if key and secret.strip() else None
    allow_trade = os.environ.get(ALLOW_TRADE_KEY_ENV, "false").strip().lower() == "true"
    return Settings(paper_mode=True, credentials=creds, allow_trade_scoped_key=allow_trade)

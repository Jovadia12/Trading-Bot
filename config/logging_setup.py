"""Logging with secret redaction.

Every handler installed here carries a filter that replaces known secret values
(API key name, API secret, and any bearer/JWT-looking token) with ``<redacted>``.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Iterable

from config.settings import API_KEY_ENV, API_SECRET_ENV

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
_BEARER_RE = re.compile(r"(Bearer\s+)[^\s'\"]+", re.IGNORECASE)
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)


class SecretRedactingFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str] = ()):
        super().__init__()
        self._secrets = sorted({s for s in secrets if s and len(s) >= 6}, key=len, reverse=True)

    def redact(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, "<redacted>")
            # also catch the secret with whitespace/newlines collapsed
            compact = "".join(s.split())
            if compact != s:
                text = text.replace(compact, "<redacted>")
        text = _PEM_RE.sub("<redacted-private-key>", text)
        text = _JWT_RE.sub("<redacted-jwt>", text)
        text = _BEARER_RE.sub(r"\1<redacted>", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # malformed args; leave record alone
            return True
        record.msg = self.redact(message)
        record.args = None
        return True


def known_secrets() -> list[str]:
    return [os.environ.get(API_KEY_ENV, ""), os.environ.get(API_SECRET_ENV, "")]


def setup_logging(level: int = logging.INFO, extra_secrets: Iterable[str] = ()) -> SecretRedactingFilter:
    flt = SecretRedactingFilter([*known_secrets(), *extra_secrets])
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    for handler in root.handlers:
        if not any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
            handler.addFilter(flt)
    root.setLevel(level)
    return flt

"""Normalization and safe inspection of Coinbase CDP API credentials.

Coinbase's CDP portal issues Ed25519 "Secret API keys" whose secret is standard base64 of
64 bytes (32-byte seed || 32-byte public key); legacy keys are EC P-256 SEC1 PEM. The key file
download is JSON: {"id"|"name": ..., "privateKey": ...}.

Values often get mangled on the way from the portal into an environment variable (macOS
TextEdit rich-text/smart quotes, inline comments, one-line PEMs, lost padding, ...). This module
repairs those *formatting* problems, validates the result cryptographically, and hands the
official SDK (``coinbase.jwt_generator``) a canonical secret. Nothing here ever returns, logs or
formats the secret or key name; inspections only describe *shape*.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

_INVISIBLE = dict.fromkeys(map(ord, "﻿​‌‍⁠­"), None)
_QUOTES = "\"'`“”‘’«»"
_PEM_RE = re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----(.*?)-----END \1-----", re.S)
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
KEY_NAME_FORMATS = {
    "organizations/<uuid>/apiKeys/<uuid>": re.compile(rf"^organizations/{_UUID}/apiKeys/{_UUID}$"),
    "<uuid> (CDP key id)": re.compile(rf"^{_UUID}$"),
}


class CredentialFormatError(ValueError):
    """The secret could not be interpreted. Messages describe shape only, never content."""


@dataclass
class SecretInfo:
    kind: str = "unknown"                 # e.g. "Ed25519 raw base64 (64 bytes: seed||public key)"
    algorithm: str = ""                   # "EdDSA" | "ES256"
    fixes: list[str] = field(default_factory=list)
    public_key_verified: Optional[bool] = None
    canonical: str = field(default="", repr=False)   # what the official SDK receives
    key_name_from_json: str = field(default="", repr=False)

    def __repr__(self) -> str:
        return f"SecretInfo(kind={self.kind!r}, algorithm={self.algorithm!r}, fixes={self.fixes!r})"


def _clean_text(value: str, fixes: list[str], what: str) -> str:
    v = value
    if v != v.translate(_INVISIBLE):
        v = v.translate(_INVISIBLE)
        fixes.append(f"{what}: removed invisible characters (BOM/zero-width)")
    v = v.strip()
    if v.startswith("export "):
        v = v[len("export "):].strip()
    # inline comment:  value  # note   (base64/PEM/key names never contain " #")
    m = re.search(r"\s+#", v)
    if m:
        v = v[: m.start()].rstrip()
        fixes.append(f"{what}: removed trailing inline comment")
    # RTF (TextEdit) leaves a trailing backslash on every line
    if v.endswith("\\") and not v.endswith("\\\\"):
        v = v[:-1].rstrip()
        fixes.append(f"{what}: removed trailing backslash (file saved as Rich Text?)")
    stripped = False
    while v and (v[0] in _QUOTES or v[-1] in _QUOTES):
        if v[0] in _QUOTES:
            v = v[1:]
        if v and v[-1] in _QUOTES:
            v = v[:-1]
        v = v.strip()
        stripped = True
    if stripped:
        fixes.append(f"{what}: removed surrounding quotes")
    return v


def normalize_key_name(value: Optional[str]) -> tuple[str, list[str]]:
    fixes: list[str] = []
    v = _clean_text(value or "", fixes, "API key")
    if v.endswith("\\n"):
        v = v[:-2]
        fixes.append("API key: removed literal \\n")
    return v, fixes


def describe_key_name(name: str) -> str:
    for label, rx in KEY_NAME_FORMATS.items():
        if rx.match(name):
            return label
    if not name:
        return "EMPTY"
    return f"UNRECOGNIZED ({len(name)} chars; expected organizations/<uuid>/apiKeys/<uuid>)"


def _b64decode_lenient(text: str, fixes: list[str]) -> bytes:
    compact = "".join(text.split())
    if re.fullmatch(r"[A-Za-z0-9\-_]+=*", compact) and re.search(r"[-_]", compact):
        compact = compact.replace("-", "+").replace("_", "/")
        fixes.append("secret: converted URL-safe base64 to standard base64")
    if not re.fullmatch(r"[A-Za-z0-9+/]+=*", compact):
        bad = sorted({c for c in compact if not re.match(r"[A-Za-z0-9+/=]", c)})
        kinds = ", ".join("whitespace" if c.isspace() else ("non-ASCII" if ord(c) > 127 else repr(c)) for c in bad)
        raise CredentialFormatError(f"secret contains characters that are not base64: {kinds}")
    body = compact.rstrip("=")
    if len(body) % 4 == 1:
        raise CredentialFormatError(f"secret base64 has an impossible length ({len(body)} chars) -- truncated?")
    padded = body + "=" * (-len(body) % 4)
    if padded != compact:
        fixes.append("secret: repaired base64 padding")
    try:
        return base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        raise CredentialFormatError("secret is not decodable base64") from None


def _pem_canonical(text: str, fixes: list[str]):
    m = _PEM_RE.search(text)
    if not m:
        raise CredentialFormatError("secret has a PEM BEGIN line but no matching END line (truncated or multi-line value cut off)")
    label, body = m.group(1), "".join(m.group(2).split())
    wrapped = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    pem = f"-----BEGIN {label}-----\n{wrapped}\n-----END {label}-----\n"
    if pem.strip() != text.strip():
        fixes.append("secret: re-formatted PEM (line breaks/spaces)")
    try:
        return serialization.load_pem_private_key(pem.encode(), password=None), label
    except (ValueError, TypeError):
        raise CredentialFormatError(f"secret PEM ({label}) could not be parsed") from None


def inspect_secret(value: Optional[str]) -> SecretInfo:
    """Parse any supported CDP secret representation. Raises CredentialFormatError (no content)."""
    info = SecretInfo()
    if not value or not value.strip():
        raise CredentialFormatError("secret is empty")
    text = _clean_text(value, info.fixes, "secret")
    if "\\n" in text or "\\r" in text:
        text = text.replace("\\r", "").replace("\\n", "\n")
        info.fixes.append("secret: converted literal \\n escapes to line breaks")
    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
            text = data["privateKey"]
        except (ValueError, KeyError, TypeError):
            raise CredentialFormatError("secret looks like JSON but has no readable 'privateKey' field") from None
        info.key_name_from_json = str(data.get("name") or data.get("id") or "")
        info.fixes.append("secret: extracted privateKey from CDP key JSON")
        return _finish(inspect_secret(text), info)

    if "BEGIN" in text:
        key, label = _pem_canonical(text, info.fixes)
        info.kind = f"PEM ({label})"
    else:
        raw = _b64decode_lenient(text, info.fixes)
        if len(raw) == 64:
            key = ed25519.Ed25519PrivateKey.from_private_bytes(raw[:32])
            pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            info.public_key_verified = pub == raw[32:]
            if not info.public_key_verified:
                raise CredentialFormatError(
                    "secret decodes to 64 bytes but the second half is not the matching Ed25519 public key "
                    "(partial copy or wrong value?)")
            info.kind = "Ed25519 raw base64 (64 bytes: seed||public key, CDP portal format)"
        elif len(raw) == 32:
            key = ed25519.Ed25519PrivateKey.from_private_bytes(raw)
            info.kind = "Ed25519 raw base64 (32-byte seed)"
        else:
            try:
                key = serialization.load_der_private_key(raw, password=None)
                info.kind = f"DER private key in base64 ({len(raw)} bytes)"
            except (ValueError, TypeError):
                raise CredentialFormatError(
                    f"secret decodes to {len(raw)} bytes; a CDP Ed25519 secret decodes to 64 bytes "
                    "(partial copy, or the API key name pasted into the secret?)") from None
    return _finish(_canonicalize(key, info), info)


def _canonicalize(key, info: SecretInfo) -> SecretInfo:
    if isinstance(key, ed25519.Ed25519PrivateKey):
        seed = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                 serialization.NoEncryption())
        pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        info.canonical = base64.b64encode(seed + pub).decode()   # the CDP portal's own format
        info.algorithm = "EdDSA"
    elif isinstance(key, ec.EllipticCurvePrivateKey):
        if key.curve.name != "secp256r1":
            raise CredentialFormatError(f"EC key on unsupported curve {key.curve.name}; Coinbase uses P-256")
        info.canonical = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                           serialization.NoEncryption()).decode()
        info.algorithm = "ES256"
    else:
        raise CredentialFormatError(f"unsupported key type {type(key).__name__}")
    return info


def _finish(inner: SecretInfo, outer: SecretInfo) -> SecretInfo:
    if inner is outer:
        return inner
    inner.fixes = outer.fixes + inner.fixes
    inner.key_name_from_json = inner.key_name_from_json or outer.key_name_from_json
    return inner


def load_key_file(path: str | Path) -> tuple[str, str]:
    """Read a CDP key JSON file (as downloaded). Returns (key_name, private_key); never logs them."""
    try:
        data = json.loads(Path(path).expanduser().read_text(encoding="utf-8-sig"))
        return str(data.get("name") or data.get("id") or ""), str(data["privateKey"])
    except FileNotFoundError:
        raise CredentialFormatError("COINBASE_API_KEY_FILE does not exist") from None
    except (ValueError, KeyError, TypeError):
        raise CredentialFormatError("COINBASE_API_KEY_FILE is not a CDP key JSON with a privateKey field") from None

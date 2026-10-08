"""Authentication: email + password, opaque server-side sessions.

The authenticated user's firm comes from the ``users`` row, never from the
request. Wallets play no role in authentication: there is no wallet login,
and discovering a wallet never links it to, or switches, a user account.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or utcnow()).isoformat(timespec="seconds")


_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class AuthContext:
    user_id: int
    firm_id: int
    email: str
    name: str | None
    firm_name: str


def create_firm(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute("INSERT INTO firms(name, created_at) VALUES (?, ?)", (name.strip(), iso()))
    return int(cur.lastrowid)


def create_user(conn: sqlite3.Connection, firm_id: int, email: str, password: str,
                name: str | None = None, role: str = "member") -> int:
    cur = conn.execute(
        "INSERT INTO users(firm_id, email, name, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
        (firm_id, email.strip().lower(), name, hash_password(password), role, iso()),
    )
    return int(cur.lastrowid)


# A fixed dummy hash so failed lookups take as long as real verifications.
_DUMMY_HASH = "scrypt$" + "00" * 16 + "$" + "00" * 32


def authenticate(conn: sqlite3.Connection, email: str, password: str) -> int | None:
    row = conn.execute("SELECT id, password_hash FROM users WHERE email = ?",
                       (email.strip().lower(),)).fetchone()
    if row is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return int(row["id"]) if verify_password(password, row["password_hash"]) else None


def create_session(conn: sqlite3.Connection, user_id: int, ttl_hours: int) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    conn.execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                 (_token_hash(token), user_id, iso(now), iso(now + timedelta(hours=ttl_hours))))
    return token


def destroy_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def resolve_session(conn: sqlite3.Connection, token: str | None) -> AuthContext | None:
    if not token:
        return None
    row = conn.execute(
        """SELECT u.id AS user_id, u.firm_id, u.email, u.name, f.name AS firm_name, s.expires_at
             FROM sessions s JOIN users u ON u.id = s.user_id JOIN firms f ON f.id = u.firm_id
            WHERE s.token_hash = ?""",
        (_token_hash(token),),
    ).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) <= utcnow():
        destroy_session(conn, token)
        return None
    return AuthContext(user_id=row["user_id"], firm_id=row["firm_id"], email=row["email"],
                       name=row["name"], firm_name=row["firm_name"])

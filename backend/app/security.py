"""Auth primitives: password hashing (bcrypt) and JWT encode/decode.

Pure functions with no DB or HTTP knowledge — callable from services. Secrets come
from config/env, never hard-coded (docs/SECURITY.md).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

# bcrypt operates on the first 72 bytes; longer inputs are truncated by the algorithm.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    pw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, token_version: int = 0) -> str:
    """Issue a signed JWT whose `sub` claim is the user id (as a string).

    `token_version` is embedded as the `tv` claim; the request path rejects a token whose
    `tv` no longer matches the user's current `token_version` (spec-03 hard-revoke).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """Return the JWT claims, or None if the token is invalid/expired."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None


def generate_refresh_token() -> str:
    """A high-entropy opaque refresh token (the value placed in the httpOnly cookie)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw: str) -> str:
    """SHA-256 hex digest stored in the DB; the plaintext token is never persisted."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

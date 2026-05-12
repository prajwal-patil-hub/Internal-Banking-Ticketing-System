"""Cryptographic primitives: password hashing, JWT, refresh-token hashing.

- Passwords use Argon2id via argon2-cffi (PHC-winning KDF, memory-hard).
- Access JWTs are short-lived (15m by default) and stateless.
- Refresh tokens are random 256-bit secrets returned to the client; we store
  only their SHA-256 hash. Rotation policy lives in `auth_service`.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()  # sane defaults: argon2id, t=3, m=64MB, p=4


# --- Passwords -------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _ph.hash(plain + settings.PASSWORD_PEPPER)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain + settings.PASSWORD_PEPPER)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


# --- JWT (access tokens) ---------------------------------------------------

TokenType = Literal["access"]


def create_access_token(
    *, subject: str, role: str, extra: dict[str, Any] | None = None
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.JWT_ACCESS_TTL_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_hex(16),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, exp


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# --- Refresh tokens (server-side hashed) -----------------------------------

def generate_refresh_token() -> tuple[str, str, datetime]:
    """Return (raw_token_for_client, sha256_hash_for_db, expiry)."""
    raw = secrets.token_urlsafe(48)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    expiry = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TTL_DAYS)
    return raw, digest, expiry


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

"""Cryptographic primitives: password hashing, JWT, refresh-token hashing.

- Passwords use Argon2id via argon2-cffi (PHC-winning KDF, memory-hard).
- Access JWTs are short-lived (15m by default) and stateless.
- Refresh tokens are random 256-bit secrets returned to the client; we store
  only their SHA-256 hash. Rotation policy lives in `auth_service`.
"""

from __future__ import annotations

import hashlib
import io
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


# --- Multi-factor authentication (TOTP) ------------------------------------

#: Minutes an MFA challenge token stays valid — long enough to read a code off
#: a phone, short enough that a leaked challenge is near-worthless.
MFA_CHALLENGE_TTL_MINUTES = 5

#: Accept the adjacent 30s step either side, covering modest clock drift.
_TOTP_VALID_WINDOW = 1


def generate_mfa_secret() -> str:
    """A fresh base32 TOTP secret."""
    import pyotp

    return pyotp.random_base32()


def mfa_provisioning_uri(secret: str, email: str, issuer: str = "SUCCESS Bank") -> str:
    """otpauth:// URI that authenticator apps read from a QR code."""
    import pyotp

    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def mfa_qr_svg(uri: str) -> str | None:
    """Inline SVG QR code for an otpauth URI, or None if unavailable.

    Returns None rather than raising when the QR library is missing — the
    enrolment screen also shows the secret for manual entry, so a container
    built before `segno` was added degrades to that instead of erroring.
    """
    try:
        import segno
    except ImportError:  # pragma: no cover - depends on the installed image
        return None

    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=5, border=2, xmldecl=False)
    return buf.getvalue().decode()


def verify_totp(secret: str, code: str) -> bool:
    """Check a 6-digit code against the secret."""
    import pyotp

    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=_TOTP_VALID_WINDOW)


def create_mfa_challenge_token(*, subject: str) -> tuple[str, datetime]:
    """Short-lived token proving the password step passed.

    Typed `mfa` rather than `access`, so `get_current_user` rejects it — a
    half-authenticated session must not reach any protected route.
    """
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=MFA_CHALLENGE_TTL_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": "mfa",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM), exp

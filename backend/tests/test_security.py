"""Unit tests for password hashing and JWT helpers."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test_secret_must_be_at_least_32_characters_long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

from app.core.security import (  # noqa: E402
    create_access_token,
    decode_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    h = hash_password("S3curePass!")
    assert verify_password("S3curePass!", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip() -> None:
    token, _ = create_access_token(subject="user-123", role="admin")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_refresh_token_hashing_is_deterministic() -> None:
    raw, digest, _ = generate_refresh_token()
    assert hash_refresh_token(raw) == digest

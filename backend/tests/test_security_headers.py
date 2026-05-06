"""Smoke check that security headers are applied to every response."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test_secret_must_be_at_least_32_characters_long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_security_headers_present() -> None:
    with TestClient(app) as client:
        r = client.get("/api/v1/healthz")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in r.headers
    assert "Permissions-Policy" in r.headers

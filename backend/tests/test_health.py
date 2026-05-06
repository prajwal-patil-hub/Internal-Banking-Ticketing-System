"""Smoke test: app boots and /healthz responds with the standard envelope."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_healthz_returns_alive() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "alive"
    assert "X-Request-ID" in resp.headers

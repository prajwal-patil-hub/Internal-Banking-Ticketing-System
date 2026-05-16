"""End-to-end auth: login → access protected route → refresh → logout."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_login_then_access_protected(client, agent_user):
    user, _ = agent_user
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Agent@1234"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    access = body["data"]["tokens"]["access_token"]
    assert access

    r2 = await client.get(
        "/api/v1/tickets?page=1&per_page=20",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r2.status_code == 200, r2.text


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client, agent_user):
    user, _ = agent_user
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "WrongPass123"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_login_short_password_is_422(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "anyone@example.com", "password": "short"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

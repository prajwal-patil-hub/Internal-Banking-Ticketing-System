"""Authorization hardening — regressions that prove the assign-to-wrong-role
and IDOR holes from the gap analysis stay closed."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User


async def _make_user(email: str, role_name: str, active: bool = True) -> User:
    async with SessionLocal() as db:
        role = (
            await db.execute(select(Role).where(Role.name == role_name))
        ).scalar_one_or_none()
        if role is None:
            role = Role(id=uuid.uuid4(), name=role_name, description=role_name)
            role.permissions = []
            db.add(role)
            await db.flush()
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                email=email,
                full_name=email.split("@")[0],
                password_hash=hash_password("Password@123"),
                role_id=role.id,
                is_active=active,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        else:
            user.is_active = active
            await db.commit()
            await db.refresh(user)
        return user


def _token(user: User) -> str:
    tok, _ = create_access_token(subject=str(user.id), role=user.role.name)
    return tok


@pytest.mark.asyncio
async def test_assign_to_branch_user_is_rejected(client, auth_headers):
    """Agents must not be able to assign tickets to branch_users — those
    accounts can't act on tickets and the assignment would silently strand."""
    branch_user = await _make_user("idor-branch@example.com", "branch_user")

    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "Cannot assign to branch user", "priority": "low"},
    )
    tid = create.json()["data"]["id"]

    r = await client.post(
        f"/api/v1/tickets/{tid}/assign",
        headers=auth_headers,
        json={"assignee_id": str(branch_user.id)},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "branch_user" in r.json()["error"]["message"]


@pytest.mark.asyncio
async def test_assign_to_inactive_user_is_rejected(client, auth_headers):
    inactive_agent = await _make_user("idor-inactive@example.com", "agent", active=False)

    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "Cannot assign to inactive", "priority": "low"},
    )
    tid = create.json()["data"]["id"]

    r = await client.post(
        f"/api/v1/tickets/{tid}/assign",
        headers=auth_headers,
        json={"assignee_id": str(inactive_agent.id)},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "inactive" in r.json()["error"]["message"]


@pytest.mark.asyncio
async def test_branch_user_cannot_view_another_users_ticket(client, auth_headers):
    """IDOR check: a branch user opening another reporter's ticket-by-id
    must get 403, not 200."""
    # The 'auth_headers' fixture user is an agent — use that account to file
    # a ticket on behalf of another (so a branch user shouldn't see it).
    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "Private to its reporter", "priority": "low"},
    )
    tid = create.json()["data"]["id"]

    # Branch user trying to read someone else's ticket
    other = await _make_user("idor-other-branch@example.com", "branch_user")
    other_token = _token(other)
    r = await client.get(
        f"/api/v1/tickets/{tid}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_comment_endpoint_is_rate_limited(client, auth_headers):
    """60 comments/min/user — burst test confirms the limiter wraps the route."""
    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "Rate-limit target", "priority": "low"},
    )
    tid = create.json()["data"]["id"]

    statuses = []
    for i in range(62):
        r = await client.post(
            f"/api/v1/tickets/{tid}/comments",
            headers=auth_headers,
            json={"body": f"flood {i}", "is_internal": False},
        )
        statuses.append(r.status_code)

    assert statuses[:60].count(201) == 60, "first 60 should pass"
    assert 429 in statuses[60:], "request 61+ should be rate-limited"

"""Coverage for the new admin/management endpoints powering the
Users, Roles, Branches, and Escalations pages.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.branch import Branch
from app.models.escalation import EscalationEvent, EscalationRule, EscalationTrigger
from app.models.role import Role
from app.models.user import User
from app.core.security import create_access_token, hash_password


async def _admin_token() -> str:
    async with SessionLocal() as db:
        role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
        if role is None:
            role = Role(id=uuid.uuid4(), name="admin", description="Admin")
            db.add(role)
            await db.flush()
        user = (
            await db.execute(select(User).where(User.email == "admin@example.com"))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                email="admin@example.com",
                full_name="Admin",
                password_hash=hash_password("Admin@1234"),
                role_id=role.id,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        token, _ = create_access_token(subject=str(user.id), role="admin")
        return token


@pytest.mark.asyncio
async def test_list_users_returns_paginated(client):
    token = await _admin_token()
    r = await client.get(
        "/api/v1/users?page=1&per_page=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert "pagination" in body["meta"]
    # at least the admin we just created
    emails = [u["email"] for u in body["data"]]
    assert "admin@example.com" in emails


@pytest.mark.asyncio
async def test_list_roles_includes_seeded(client):
    token = await _admin_token()
    r = await client.get("/api/v1/roles", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    names = [row["name"] for row in r.json()["data"]]
    assert "admin" in names


@pytest.mark.asyncio
async def test_list_branches_empty_ok(client):
    token = await _admin_token()
    r = await client.get("/api/v1/branches", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


@pytest.mark.asyncio
async def test_create_branch_then_list(client):
    token = await _admin_token()
    create = await client.post(
        "/api/v1/branches",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": "MUM01", "name": "Mumbai Fort", "region": "West", "ifsc": "SBLK0000001"},
    )
    assert create.status_code == 201, create.text
    assert create.json()["data"]["code"] == "MUM01"

    listed = await client.get(
        "/api/v1/branches?search=Mumbai",
        headers={"Authorization": f"Bearer {token}"},
    )
    codes = [b["code"] for b in listed.json()["data"]]
    assert "MUM01" in codes


@pytest.mark.asyncio
async def test_create_branch_rejects_duplicate_code(client):
    token = await _admin_token()
    await client.post(
        "/api/v1/branches",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": "DUP01", "name": "Duplicate Test"},
    )
    second = await client.post(
        "/api/v1/branches",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": "DUP01", "name": "Should Conflict"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_list_escalation_rules_and_events(client):
    token = await _admin_token()

    # Seed a real ticket -> rule -> event so FKs resolve.
    async with SessionLocal() as db:
        from datetime import datetime, timezone
        from app.models.ticket import Ticket, TicketPriority, TicketSource, TicketStatus

        admin = (await db.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        ticket = Ticket(
            id=uuid.uuid4(),
            ticket_number="TKT-ESC-001",
            title="Escalation test ticket",
            status=TicketStatus.NEW,
            priority=TicketPriority.CRITICAL,
            source=TicketSource.PORTAL,
            reporter_id=admin.id,
        )
        db.add(ticket)
        await db.flush()

        rule = EscalationRule(
            id=uuid.uuid4(),
            name="Critical SLA breach",
            trigger=EscalationTrigger.SLA_BREACH,
            trigger_after_minutes=60,
            escalate_to_role="supervisor",
            priority_threshold="critical",
            is_active=True,
        )
        db.add(rule)
        await db.flush()

        event = EscalationEvent(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            rule_id=rule.id,
            trigger=EscalationTrigger.SLA_BREACH,
            triggered_at=datetime.now(timezone.utc),
            reason="60-minute SLA exceeded",
        )
        db.add(event)
        await db.commit()

    rules = await client.get(
        "/api/v1/escalations/rules", headers={"Authorization": f"Bearer {token}"}
    )
    assert rules.status_code == 200, rules.text
    assert any(r["name"] == "Critical SLA breach" for r in rules.json()["data"])

    events = await client.get(
        "/api/v1/escalations/events", headers={"Authorization": f"Bearer {token}"}
    )
    assert events.status_code == 200, events.text
    assert len(events.json()["data"]) >= 1

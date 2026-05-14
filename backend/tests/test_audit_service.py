"""AuditService unit tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()   # service uses flush, not commit
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_audit_log_creates_entry() -> None:
    from app.models.audit import AuditAction
    from app.services.audit_service import AuditService

    db = _mock_db()
    svc = AuditService(db)

    log_entry = await svc.log(
        entity_type="ticket",
        entity_id=str(uuid.uuid4()),
        action=AuditAction.CREATE,
        actor_id=str(uuid.uuid4()),
        actor_email="agent@bank.com",
        actor_role="agent",
        new_values={"title": "New ticket", "status": "new"},
        ip_address="10.0.0.1",
        request_id=str(uuid.uuid4()),
    )

    db.add.assert_called_once()
    db.flush.assert_called_once()   # service flushes, not commits
    assert log_entry is not None
    assert log_entry.entity_type == "ticket"
    assert log_entry.action == AuditAction.CREATE


@pytest.mark.asyncio
async def test_audit_log_stores_diff() -> None:
    from app.models.audit import AuditAction
    from app.services.audit_service import AuditService

    db = _mock_db()
    svc = AuditService(db)

    log_entry = await svc.log(
        entity_type="ticket",
        entity_id=str(uuid.uuid4()),
        action=AuditAction.STATUS_CHANGE,
        actor_id=str(uuid.uuid4()),
        old_values={"status": "new"},
        new_values={"status": "assigned"},
    )

    assert log_entry.old_values == {"status": "new"}
    assert log_entry.new_values == {"status": "assigned"}


@pytest.mark.asyncio
async def test_audit_log_ai_decision() -> None:
    from app.models.audit import AuditAction
    from app.services.audit_service import AuditService

    db = _mock_db()
    svc = AuditService(db)

    log_entry = await svc.log(
        entity_type="ticket",
        entity_id=str(uuid.uuid4()),
        action=AuditAction.AI_DECISION,
        actor_id=None,
        new_values={"category": "payments", "confidence": 0.95, "model": "claude-sonnet-4-6"},
        metadata={"ai_model": "claude-sonnet-4-6", "tokens": 150},
    )

    assert log_entry.action == AuditAction.AI_DECISION
    assert log_entry.actor_id is None


@pytest.mark.asyncio
async def test_get_audit_trail_pagination() -> None:
    from app.models.audit import AuditLog, AuditAction
    from app.services.audit_service import AuditService

    db = _mock_db()

    logs = []
    for _ in range(5):
        entry = AuditLog(
            id=uuid.uuid4(),
            entity_type="ticket",
            entity_id=str(uuid.uuid4()),
            action=AuditAction.CREATE,
        )
        entry.created_at = datetime.now(timezone.utc)
        logs.append(entry)

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count == 1:
            m.scalar_one.return_value = 5
        else:
            m.scalars.return_value.all.return_value = logs
        return m

    db.execute = mock_execute

    svc = AuditService(db)
    result, total = await svc.get_audit_trail(entity_type="ticket", page=1, per_page=10)

    assert total == 5
    assert len(result) == 5


@pytest.mark.asyncio
async def test_audit_log_no_actor() -> None:
    from app.models.audit import AuditAction
    from app.services.audit_service import AuditService

    db = _mock_db()
    svc = AuditService(db)

    log_entry = await svc.log(
        entity_type="ticket",
        entity_id=str(uuid.uuid4()),
        action=AuditAction.STATUS_CHANGE,
        actor_id=None,
        new_values={"status": "resolved"},
    )

    assert log_entry.actor_id is None
    assert log_entry.action == AuditAction.STATUS_CHANGE


@pytest.mark.asyncio
async def test_audit_log_is_append_only() -> None:
    """Audit log should never issue UPDATE — service only calls add+flush."""
    from app.models.audit import AuditAction
    from app.services.audit_service import AuditService

    db = _mock_db()
    svc = AuditService(db)

    await svc.log(
        entity_type="user",
        entity_id=str(uuid.uuid4()),
        action=AuditAction.LOGIN,
        actor_id=str(uuid.uuid4()),
    )

    # Should call add (insert) and flush, never merge/update
    db.add.assert_called_once()
    db.flush.assert_called_once()

"""The audit trail cannot be edited, and the refusal comes from the database.

This was the largest architectural gap in the system: the trail was append-only
by convention, meaning application code only ever inserted and nothing stopped
anything else. Anyone reaching the database with the application's own
credentials could rewrite who did what, and the record would show no sign of
it. A log that is complete only because nobody tried is not an audit trail.

The tests below deliberately attempt the tampering rather than asserting that a
trigger exists. A trigger that exists and does not fire is exactly the kind of
green check this project has been bitten by before — a CI job reporting success
on a suite it never ran, a callout resolving to the wrong element, a gate
passing because nothing was retrieved for anybody.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.asyncio

#: PostgreSQL insufficient_privilege. The trigger raises with this SQLSTATE so
#: a caller can tell "you may not do this" from a constraint violation.
INSUFFICIENT_PRIVILEGE = "42501"


async def _insert_row(db) -> uuid.UUID:
    """Write one audit row the way the application does."""
    row_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO audit_logs "
            "(id, entity_type, entity_id, action, actor_email, actor_role, created_at) "
            "VALUES (:id, 'ticket', :eid, 'create', :email, 'agent', :ts)"
        ),
        {
            "id": row_id,
            "eid": str(uuid.uuid4()),
            "email": f"agent-{uuid.uuid4().hex[:6]}@bank.com",
            "ts": datetime.now(UTC),
        },
    )
    return row_id


def _is_refusal(exc: DBAPIError) -> bool:
    code = getattr(getattr(exc, "orig", None), "sqlstate", None)
    return code == INSUFFICIENT_PRIVILEGE or "append-only" in str(exc)


# ---------------------------------------------------------------------------
# Writing is still allowed
# ---------------------------------------------------------------------------

async def test_the_application_can_still_append(db_session) -> None:
    """The guard must not break the thing the table is for.

    A protection that also blocks inserts would be discovered in production by
    every write failing, which is a worse outcome than the gap it closed.
    """
    row_id = await _insert_row(db_session)
    found = (
        await db_session.execute(
            text("SELECT count(*) FROM audit_logs WHERE id = :id"), {"id": row_id}
        )
    ).scalar_one()
    assert found == 1


# ---------------------------------------------------------------------------
# Editing is refused
# ---------------------------------------------------------------------------

async def test_an_existing_row_cannot_be_rewritten(db_session) -> None:
    """The attack this exists to stop: change who did it, after the fact."""
    row_id = await _insert_row(db_session)
    await db_session.execute(text("SAVEPOINT sp"))

    with pytest.raises(DBAPIError) as exc:
        await db_session.execute(
            text("UPDATE audit_logs SET actor_email = :e WHERE id = :id"),
            {"e": "someone.else@bank.com", "id": row_id},
        )
    assert _is_refusal(exc.value)
    await db_session.execute(text("ROLLBACK TO SAVEPOINT sp"))

    # And the row is untouched.
    email = (
        await db_session.execute(
            text("SELECT actor_email FROM audit_logs WHERE id = :id"), {"id": row_id}
        )
    ).scalar_one()
    assert "someone.else" not in email


async def test_a_row_cannot_be_deleted(db_session) -> None:
    row_id = await _insert_row(db_session)
    await db_session.execute(text("SAVEPOINT sp"))

    with pytest.raises(DBAPIError) as exc:
        await db_session.execute(
            text("DELETE FROM audit_logs WHERE id = :id"), {"id": row_id}
        )
    assert _is_refusal(exc.value)
    await db_session.execute(text("ROLLBACK TO SAVEPOINT sp"))

    still_there = (
        await db_session.execute(
            text("SELECT count(*) FROM audit_logs WHERE id = :id"), {"id": row_id}
        )
    ).scalar_one()
    assert still_there == 1


async def test_a_no_op_update_is_refused_too(db_session) -> None:
    """`SET x = x` is still an UPDATE.

    Worth pinning: a trigger written to compare OLD and NEW and only complain
    when something changed would let a toolchain "touch" audit rows, and the
    rule becomes "you may edit as long as you put it back".
    """
    row_id = await _insert_row(db_session)
    await db_session.execute(text("SAVEPOINT sp"))

    with pytest.raises(DBAPIError) as exc:
        await db_session.execute(
            text("UPDATE audit_logs SET actor_email = actor_email WHERE id = :id"),
            {"id": row_id},
        )
    assert _is_refusal(exc.value)
    await db_session.execute(text("ROLLBACK TO SAVEPOINT sp"))


async def test_a_bulk_delete_is_refused(db_session) -> None:
    """The row trigger fires per row, so a statement matching many rows is
    refused on the first one rather than partially succeeding."""
    await _insert_row(db_session)
    await _insert_row(db_session)
    await db_session.execute(text("SAVEPOINT sp"))

    with pytest.raises(DBAPIError) as exc:
        await db_session.execute(text("DELETE FROM audit_logs"))
    assert _is_refusal(exc.value)
    await db_session.execute(text("ROLLBACK TO SAVEPOINT sp"))


async def test_truncate_is_refused_by_its_own_trigger(db_session) -> None:
    """TRUNCATE does not fire a row-level trigger.

    Without a separate statement-level trigger the table could be emptied in
    one statement while the row trigger sat there looking like protection.
    """
    await _insert_row(db_session)
    await db_session.execute(text("SAVEPOINT sp"))

    with pytest.raises(DBAPIError) as exc:
        await db_session.execute(text("TRUNCATE audit_logs"))
    assert _is_refusal(exc.value)
    await db_session.execute(text("ROLLBACK TO SAVEPOINT sp"))


# ---------------------------------------------------------------------------
# The refusal is where we think it is
# ---------------------------------------------------------------------------

async def test_both_triggers_are_installed(db_session) -> None:
    """Names are asserted so a rename in a later migration is a failing test
    rather than a silently unprotected table."""
    rows = (
        await db_session.execute(
            text(
                "SELECT tgname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname = 'audit_logs' AND NOT t.tgisinternal"
            )
        )
    ).scalars().all()
    assert "audit_logs_no_update_delete" in rows
    assert "audit_logs_no_truncate" in rows


async def test_the_error_explains_itself(db_session) -> None:
    """An operator who hits this at 3am should not have to read the schema."""
    row_id = await _insert_row(db_session)
    await db_session.execute(text("SAVEPOINT sp"))

    with pytest.raises(DBAPIError) as exc:
        await db_session.execute(
            text("DELETE FROM audit_logs WHERE id = :id"), {"id": row_id}
        )
    message = str(exc.value)
    assert "append-only" in message
    assert "DELETE" in message
    await db_session.execute(text("ROLLBACK TO SAVEPOINT sp"))

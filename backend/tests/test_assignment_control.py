"""Leave windows, the SQL that filters on them, and the settings clamp.

The leave predicate is written twice — once in Python for serialising a user,
once in SQL so the lowest-workload ordering only considers people who can
actually take the work. Two implementations of one rule is exactly the shape
of bug that ships quietly, so these tests pin them against each other.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.services.routing_service import _available_on, is_on_leave

TODAY = date(2026, 8, 18)


def _user(leave_from: date | None = None, leave_to: date | None = None):
    from app.models.user import User

    u = User(
        id=uuid.uuid4(),
        email=f"u-{uuid.uuid4().hex[:6]}@bank.com",
        full_name="Test User",
        password_hash="x",
        role_id=uuid.uuid4(),
        is_active=True,
        mfa_enabled=False,
        failed_login_count=0,
    )
    u.leave_from = leave_from
    u.leave_to = leave_to
    u.created_at = u.updated_at = datetime.now(UTC)
    return u


# --- the Python side --------------------------------------------------------

@pytest.mark.parametrize(
    ("leave_from", "leave_to", "expected", "why"),
    [
        (None, None, False, "no leave recorded"),
        (date(2026, 8, 10), date(2026, 8, 25), True, "today inside the window"),
        (date(2026, 8, 18), date(2026, 8, 25), True, "first day is inclusive"),
        (date(2026, 8, 10), date(2026, 8, 18), True, "last day is inclusive"),
        (date(2026, 8, 19), date(2026, 8, 25), False, "starts tomorrow"),
        (date(2026, 8, 1), date(2026, 8, 17), False, "ended yesterday"),
        (date(2026, 8, 10), None, True, "open-ended leave has not ended"),
        (None, date(2026, 8, 25), True, "open start, end in the future"),
        (None, date(2026, 8, 17), False, "open start, already ended"),
    ],
)
def test_is_on_leave(leave_from, leave_to, expected, why):
    assert is_on_leave(_user(leave_from, leave_to), TODAY) is expected, why


def test_leave_expires_without_anyone_clearing_it():
    """The whole reason leave is a date range rather than a toggle."""
    u = _user(date(2026, 8, 10), date(2026, 8, 15))
    assert is_on_leave(u, date(2026, 8, 12)) is True
    assert is_on_leave(u, date(2026, 8, 16)) is False


# --- the SQL side, checked against the Python side --------------------------

@pytest.mark.asyncio
async def test_sql_predicate_matches_python(db_session):
    """`_available_on` must select exactly the users `is_on_leave` says are free.

    Both encode one rule. If they disagree, the assign dropdown and the router
    disagree about who is available, and the discrepancy only shows up as
    tickets landing on someone who is away.
    """
    from sqlalchemy import select

    from app.models.role import Role
    from app.models.user import User

    role = Role(id=uuid.uuid4(), name=f"agent-{uuid.uuid4().hex[:6]}", description="")
    db_session.add(role)
    await db_session.flush()

    windows = [
        (None, None),
        (TODAY - timedelta(days=8), TODAY + timedelta(days=7)),
        (TODAY, TODAY + timedelta(days=1)),
        (TODAY - timedelta(days=1), TODAY),
        (TODAY + timedelta(days=1), TODAY + timedelta(days=5)),
        (TODAY - timedelta(days=9), TODAY - timedelta(days=1)),
        (TODAY - timedelta(days=3), None),
        (None, TODAY + timedelta(days=2)),
        (None, TODAY - timedelta(days=1)),
    ]
    made = []
    for i, (lf, lt) in enumerate(windows):
        u = User(
            email=f"leave-probe-{i}-{uuid.uuid4().hex[:6]}@bank.com",
            full_name=f"Probe {i}",
            password_hash="x",
            role_id=role.id,
            is_active=True,
            leave_from=lf,
            leave_to=lt,
        )
        db_session.add(u)
        made.append(u)
    await db_session.flush()

    ids = {u.id for u in made}
    rows = (await db_session.execute(
        select(User).where(User.id.in_(ids), _available_on(TODAY))
    )).scalars().all()

    from_sql = {u.id for u in rows}
    from_python = {u.id for u in made if not is_on_leave(u, TODAY)}
    assert from_sql == from_python

    # Guard against a vacuous pass: two empty sets are equal, and so are two
    # full ones. The fixtures span both states, so the predicate must have
    # actually discriminated between them.
    assert 0 < len(from_sql) < len(ids), (
        f"predicate did not discriminate: {len(from_sql)} of {len(ids)} available"
    )


# --- the delay setting ------------------------------------------------------

def test_delay_is_clamped_to_a_sane_range():
    """A zero delay would restore assign-on-creation; a huge one parks tickets."""
    from app.services.settings_service import MAX_DELAY_HOURS, MIN_DELAY_HOURS, _clamp

    assert _clamp(0) == MIN_DELAY_HOURS
    assert _clamp(-5) == MIN_DELAY_HOURS
    assert _clamp(10_000) == MAX_DELAY_HOURS
    assert _clamp(4) == 4


@pytest.mark.asyncio
async def test_delay_falls_back_when_the_row_is_missing_or_unreadable(db_session):
    """Neither an absent nor a corrupt settings row may stop tickets being assigned.

    The starting state is set explicitly rather than assumed. An earlier
    version asserted the default on the assumption that no row existed, which
    passed until something else in the environment had written one — a test
    that depends on ambient state is a test that reports on the environment
    rather than the code.
    """
    from sqlalchemy import delete

    from app.models.assignment import (
        AUTO_ASSIGN_DELAY_HOURS,
        AUTO_ASSIGN_DELAY_HOURS_DEFAULT,
        SystemSetting,
    )
    from app.services.settings_service import SettingsService

    svc = SettingsService(db_session)

    # Rolled back with the fixture's transaction, so this does not disturb
    # whatever the database held.
    await db_session.execute(
        delete(SystemSetting).where(SystemSetting.key == AUTO_ASSIGN_DELAY_HOURS)
    )
    await db_session.flush()
    db_session.expunge_all()
    assert await svc.get_auto_assign_delay_hours() == AUTO_ASSIGN_DELAY_HOURS_DEFAULT

    await svc.set_raw(AUTO_ASSIGN_DELAY_HOURS, "not-a-number", None)
    assert await svc.get_auto_assign_delay_hours() == AUTO_ASSIGN_DELAY_HOURS_DEFAULT


@pytest.mark.asyncio
async def test_delay_round_trips(db_session):
    from app.services.settings_service import SettingsService

    svc = SettingsService(db_session)
    assert await svc.set_auto_assign_delay_hours(6, None) == 6
    assert await svc.get_auto_assign_delay_hours() == 6

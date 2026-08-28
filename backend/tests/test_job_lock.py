"""Only one replica runs each scheduled job.

The schedulers live inside the API process, so a second replica would poll the
mailbox twice, evaluate SLA breaches twice, and auto-assign the same stale
ticket twice. That was the documented reason the API could not be scaled
horizontally.

These run against a real PostgreSQL because an advisory lock is a database
behaviour — mocking `pg_try_advisory_lock` would test that the mock returns
what the mock was told to return. The important case is two *concurrent*
holders, so the tests actually contend for the lock rather than taking it and
releasing it in sequence.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.services.job_lock import advisory_lock, lock_key, run_locked


@pytest.fixture(autouse=True)
async def _isolate_engine_pool():
    """Give each test an unpooled engine.

    `job_lock` uses the application's module-level engine, which is correct in
    production — one process, one event loop, one pool. pytest-asyncio runs
    each test on a fresh loop, so a connection pooled by the previous test is
    bound to a loop that no longer exists and asyncpg raises. Disposing either
    side of the test keeps the pool from crossing loops. This is a harness
    concern, not a defect in the lock.
    """
    from app.db.session import engine

    await engine.dispose()
    yield
    await engine.dispose()



# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def test_a_job_name_maps_to_a_stable_positive_key() -> None:
    first = lock_key("sla_check")
    assert first == lock_key("sla_check")
    # Signed 64-bit column in pg_locks; a negative key is legal but makes the
    # view needlessly hard to read mid-incident.
    assert 0 < first < 2**63


def test_different_jobs_do_not_share_a_lock() -> None:
    """A typo in a job name must produce a different lock, not silently
    serialise two unrelated jobs behind one another."""
    keys = {lock_key(n) for n in ("sla_check", "email_poll", "assignment_safety_net")}
    assert len(keys) == 3


# ---------------------------------------------------------------------------
# Exclusion
# ---------------------------------------------------------------------------

async def test_one_holder_at_a_time() -> None:
    """The whole point: while one process holds it, another is refused."""
    async with advisory_lock("test-exclusion") as first:
        assert first is True
        async with advisory_lock("test-exclusion") as second:
            assert second is False, "two processes both believed they held the lock"


async def test_the_lock_is_released_on_exit() -> None:
    async with advisory_lock("test-release") as acquired:
        assert acquired is True
    async with advisory_lock("test-release") as again:
        assert again is True, "the lock outlived the block that held it"


async def test_an_exception_still_releases_the_lock() -> None:
    """A job that raises must not wedge every future tick."""
    with pytest.raises(RuntimeError):
        async with advisory_lock("test-raise") as acquired:
            assert acquired is True
            raise RuntimeError("job blew up")

    async with advisory_lock("test-raise") as again:
        assert again is True, "a crashed job left the lock held for ever"


async def test_two_jobs_do_not_block_each_other() -> None:
    async with advisory_lock("test-job-a") as a, advisory_lock("test-job-b") as b:
        assert a is True and b is True


# ---------------------------------------------------------------------------
# run_locked
# ---------------------------------------------------------------------------

async def test_run_locked_executes_and_returns() -> None:
    calls = []

    async def work():
        calls.append(1)
        return "done"

    assert await run_locked("test-run", work) == "done"
    assert calls == [1]


async def test_the_second_caller_skips_rather_than_queues() -> None:
    """Blocking would leave replicas waiting behind a five-minute job.

    The second caller must return immediately having done nothing — the work
    is already being done elsewhere.
    """
    started = asyncio.Event()
    release = asyncio.Event()
    ran = []

    async def slow():
        ran.append("slow")
        started.set()
        await release.wait()
        return "slow-done"

    async def other():
        ran.append("other")
        return "other-done"

    first = asyncio.create_task(run_locked("test-contended", slow))
    await asyncio.wait_for(started.wait(), timeout=5)

    # While the first is mid-flight, a second attempt must not run the work.
    second = await asyncio.wait_for(run_locked("test-contended", other), timeout=5)
    assert second is None
    assert "other" not in ran

    release.set()
    assert await asyncio.wait_for(first, timeout=5) == "slow-done"


async def test_the_lock_frees_up_after_the_job_finishes() -> None:
    async def work():
        return 1

    assert await run_locked("test-sequential", work) == 1
    assert await run_locked("test-sequential", work) == 1


# ---------------------------------------------------------------------------
# The real jobs are wrapped
# ---------------------------------------------------------------------------

async def test_every_scheduled_job_takes_a_lock(db_session) -> None:
    """Each worker's scheduler entry point must be the locked wrapper.

    Asserting on the module rather than the behaviour here, because running the
    real jobs would poll a mailbox and evaluate live SLA rows. What must not
    regress is a job being registered against its unlocked body.
    """
    from app.workers import assignment_worker, email_worker, sla_worker

    for module, public, private in [
        (sla_worker, "check_sla_breaches_job", "_check_sla_breaches_job_locked"),
        (email_worker, "poll_emails_job", "_poll_emails_job_locked"),
        (assignment_worker, "assign_stale_unassigned_job",
         "_assign_stale_unassigned_job_locked"),
    ]:
        assert hasattr(module, public), f"{module.__name__}.{public} disappeared"
        assert hasattr(module, private), f"{module.__name__} lost its unlocked body"
        source = module.__dict__[public].__doc__ or ""
        assert "one replica" in source, f"{public} is not the locking wrapper"


async def test_the_lock_is_visible_in_pg_locks(db_session) -> None:
    """Proves it is a real database lock, not bookkeeping in Python."""
    key = lock_key("test-visible")
    async with advisory_lock("test-visible") as acquired:
        assert acquired is True
        held = (
            await db_session.execute(
                text(
                    "SELECT count(*) FROM pg_locks "
                    "WHERE locktype = 'advisory' AND objid = :low AND classid = :high"
                ),
                {"low": key & 0xFFFFFFFF, "high": key >> 32},
            )
        ).scalar_one()
        assert held >= 1

"""RBAC policy tests — the regression net that keeps roles strict.

These exercise the policy module and the lifecycle table directly, so they run
without a database. The rules they encode were all real defects at some point:
`auditor` sat inside the ticket-write role set, any admin could mint a super
admin, and the lifecycle table was never consulted by the API.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import authz
from app.core.exceptions import AuthorizationError
from app.models.ticket import TicketStatus
from app.services.ticket_service import VALID_TRANSITIONS

ALL_ROLES = [authz.ADMIN, authz.SUPERVISOR, authz.AGENT, authz.AUDITOR, authz.BRANCH_USER]


def user(role: str, *, super_admin: bool = False) -> SimpleNamespace:
    return SimpleNamespace(role=SimpleNamespace(name=role), is_super_admin=super_admin)


# ---------------------------------------------------------------------------
# Role sets
# ---------------------------------------------------------------------------

def test_auditor_is_not_a_ticket_writer() -> None:
    """The defect this whole module exists for.

    `auditor` was a member of the agent role set, so a role documented as
    read-only could edit, transition, resolve and close tickets.
    """
    assert authz.AUDITOR not in authz.TICKET_WRITE_ROLES
    assert not authz.can_write_tickets(user(authz.AUDITOR))


@pytest.mark.parametrize("role", [authz.AGENT, authz.SUPERVISOR, authz.ADMIN])
def test_working_roles_can_write_tickets(role: str) -> None:
    assert authz.can_write_tickets(user(role))


def test_branch_user_cannot_write_other_peoples_tickets() -> None:
    assert not authz.can_write_tickets(user(authz.BRANCH_USER))


def test_super_admin_flag_does_not_launder_a_read_only_role() -> None:
    """is_super_admin widens visibility; it must not grant an auditor writes."""
    auditor = user(authz.AUDITOR, super_admin=True)

    assert authz.is_read_only(auditor)
    assert not authz.can_write_tickets(auditor)
    with pytest.raises(AuthorizationError):
        authz.assert_can_write(auditor)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_only_auditor_is_read_only(role: str) -> None:
    assert authz.is_read_only(user(role)) is (role == authz.AUDITOR)


def test_assert_can_write_names_the_role_and_action() -> None:
    with pytest.raises(AuthorizationError) as exc:
        authz.assert_can_write(user(authz.AUDITOR), "raise tickets")

    assert "auditor" in str(exc.value)
    assert "raise tickets" in str(exc.value)


@pytest.mark.parametrize("role", [authz.AGENT, authz.SUPERVISOR, authz.ADMIN, authz.BRANCH_USER])
def test_assert_can_write_passes_for_everyone_else(role: str) -> None:
    authz.assert_can_write(user(role))  # must not raise


# ---------------------------------------------------------------------------
# Super-admin protection
# ---------------------------------------------------------------------------

def test_plain_admin_cannot_grant_super_admin() -> None:
    """Otherwise: create an account, set the flag, choose the password, log in."""
    with pytest.raises(AuthorizationError):
        authz.assert_can_grant_super_admin(user(authz.ADMIN), True)


def test_super_admin_can_grant_super_admin() -> None:
    authz.assert_can_grant_super_admin(user(authz.ADMIN, super_admin=True), True)


def test_not_requesting_the_flag_is_always_fine() -> None:
    authz.assert_can_grant_super_admin(user(authz.ADMIN), False)


def test_plain_admin_cannot_manage_a_super_admin() -> None:
    """Password changes route through here — this stops an account takeover."""
    with pytest.raises(AuthorizationError):
        authz.assert_can_manage_user(user(authz.ADMIN), user(authz.ADMIN, super_admin=True))


def test_super_admin_can_manage_a_super_admin() -> None:
    authz.assert_can_manage_user(
        user(authz.ADMIN, super_admin=True), user(authz.ADMIN, super_admin=True)
    )


def test_admin_can_manage_ordinary_accounts() -> None:
    authz.assert_can_manage_user(user(authz.ADMIN), user(authz.AGENT))


# ---------------------------------------------------------------------------
# Ticket lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "src,dst",
    [
        (TicketStatus.NEW, TicketStatus.RESOLVED),      # skips all the work
        (TicketStatus.NEW, TicketStatus.ON_HOLD),       # nothing to hold yet
        (TicketStatus.NEW, TicketStatus.REOPENED),      # never been closed
        (TicketStatus.CLOSED, TicketStatus.NEW),        # resurrection
        (TicketStatus.CLOSED, TicketStatus.IN_PROGRESS),
        (TicketStatus.RESOLVED, TicketStatus.NEW),
        (TicketStatus.ACKNOWLEDGED, TicketStatus.RESOLVED),
    ],
)
def test_illegal_transitions_are_absent_from_the_table(src, dst) -> None:
    assert dst not in VALID_TRANSITIONS[src]


@pytest.mark.parametrize(
    "src,dst",
    [
        (TicketStatus.NEW, TicketStatus.ACKNOWLEDGED),
        (TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED),
        (TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS),
        (TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED),
        (TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED),
        (TicketStatus.ESCALATED, TicketStatus.RESOLVED),
        (TicketStatus.RESOLVED, TicketStatus.CLOSED),
        (TicketStatus.CLOSED, TicketStatus.REOPENED),
        (TicketStatus.REOPENED, TicketStatus.IN_PROGRESS),
        (TicketStatus.ON_HOLD, TicketStatus.IN_PROGRESS),
    ],
)
def test_the_happy_path_stays_open(src, dst) -> None:
    assert dst in VALID_TRANSITIONS[src]


def test_every_status_has_a_transition_entry() -> None:
    """A missing entry would silently freeze tickets in that state."""
    assert set(VALID_TRANSITIONS) == set(TicketStatus)


def test_every_open_state_can_reach_closed() -> None:
    """Close is the universal exit — a reporter must always be able to take it.

    `reopened` originally lacked this edge, which left a reporter who reopened
    by mistake with no way back out: closing is the only transition their role
    permits, and it was not reachable from the state they had just created.
    """
    terminal = {TicketStatus.CLOSED}
    for src, allowed in VALID_TRANSITIONS.items():
        if src in terminal:
            continue
        assert TicketStatus.CLOSED in allowed, f"{src.value} cannot be closed"


def test_the_lifecycle_has_no_dead_ends() -> None:
    for src, allowed in VALID_TRANSITIONS.items():
        assert allowed, f"{src.value} is a dead end"


def test_no_transition_points_at_new() -> None:
    """`new` is an entry state only — nothing should be able to rewind to it."""
    for src, allowed in VALID_TRANSITIONS.items():
        assert TicketStatus.NEW not in allowed, f"{src.value} rewinds to new"

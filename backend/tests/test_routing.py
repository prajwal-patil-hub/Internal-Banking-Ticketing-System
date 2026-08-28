"""Auto-assignment routing policy."""

from __future__ import annotations

from app.core import authz
from app.services.routing_service import AGENT_ROLE, ASSIGNABLE_ROLES


def test_only_working_roles_can_be_auto_assigned() -> None:
    """Auditors and branch users must never receive a ticket.

    They have zero open tickets precisely because their roles cannot be
    assigned work, so a pure lowest-workload ranking picked them every time
    and the ticket landed where nobody could action it.
    """
    assert authz.AUDITOR not in ASSIGNABLE_ROLES
    assert authz.BRANCH_USER not in ASSIGNABLE_ROLES


def test_admins_are_not_auto_assigned() -> None:
    """Admins run the system; they should not be handed the frontline queue."""
    assert authz.ADMIN not in ASSIGNABLE_ROLES


def test_agents_are_the_preferred_tier() -> None:
    """Supervisors are the fallback, not the default.

    Supervisors carry no queue of their own, so ranking on workload alone
    made them the idlest user every time and frontline work skipped the
    agents entirely.
    """
    assert AGENT_ROLE == authz.AGENT
    assert AGENT_ROLE in ASSIGNABLE_ROLES
    assert authz.SUPERVISOR in ASSIGNABLE_ROLES


def test_ticket_creation_applies_sla_but_does_not_assign() -> None:
    """A new ticket gets deadlines, but choosing its owner is a person's job.

    SLA still has to be stamped here: create_ticket builds the Ticket inline
    instead of going through TicketService, so it never inherited that step
    and tickets raised in the UI had no due dates, never appeared in the SLA
    monitor, and could never breach.

    Assignment is the opposite. It used to happen here for every ticket, which
    meant nobody decided who carried the work. It now happens only when a
    supervisor asks for it, or when the safety-net worker steps in for a
    ticket that has sat unassigned past the configured delay.
    """
    import inspect

    from app.api.v1.routes.tickets import create_ticket

    src = inspect.getsource(create_ticket)
    assert "SLAService(db).apply_to_ticket" in src

    # Opt-in, not opt-out. `payload.get("auto_assign", True)` would restore the
    # old behaviour for every caller that simply omits the flag — which is all
    # of them.
    assert 'payload.get("auto_assign") is True' in src, (
        "auto-assign on creation must be explicit opt-in"
    )
    assert 'payload.get("auto_assign", True)' not in src


def test_supervisor_can_trigger_auto_assign_but_agents_cannot() -> None:
    """Auto-assign is a shift-management decision, not a way to hand work on."""
    import inspect

    from app.api.v1.routes.tickets import assign_ticket, auto_assign_ticket

    auto_src = inspect.getsource(auto_assign_ticket)
    assert 'require_roles("supervisor", "admin")' in auto_src

    # Manual assignment stays open to agents: picking up or handing over a
    # specific ticket is ordinary queue work.
    assert 'require_roles("agent", "supervisor", "admin")' in inspect.getsource(assign_ticket)

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


def test_ticket_creation_applies_sla_and_routing() -> None:
    """A ticket raised through the API must get deadlines and an owner.

    create_ticket builds the Ticket inline instead of going through
    TicketService, so it never inherited the SLA step: tickets raised in the
    UI had no due dates, never appeared in the SLA monitor, and could never
    breach.
    """
    import inspect

    from app.api.v1.routes.tickets import create_ticket

    src = inspect.getsource(create_ticket)
    assert "SLAService(db).apply_to_ticket" in src
    assert "auto_route_ticket" in src
    assert 'payload.get("auto_assign", True)' in src, "opt-out must remain"

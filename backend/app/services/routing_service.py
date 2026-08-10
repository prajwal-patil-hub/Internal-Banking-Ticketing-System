"""Routing service — intelligent ticket assignment based on workload and specialization.

Algorithm (in priority order):
1. Match agents whose branch/department aligns with the ticket's category/department.
2. Among those, pick the one with the fewest currently open tickets.
3. If no specialization match, fall back to any active agent by lowest open-ticket count.
4. If no agent is available, return None.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.logging import get_logger
from app.models.role import Role
from app.models.ticket import OPEN_STATUS_VALUES as _OPEN_STATUSES
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User

log = get_logger(__name__)

#: The role that should normally receive new work.
AGENT_ROLE = authz.AGENT

#: Roles that may receive an auto-assigned ticket at all. Admins are excluded
#: on purpose: they administer the system rather than working a queue, and
#: having the lowest workload would funnel every new ticket to them.
ASSIGNABLE_ROLES = (authz.AGENT, authz.SUPERVISOR)



class RoutingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Workload query
    # ------------------------------------------------------------------

    async def get_agent_workload(self) -> list[dict]:
        """Return a list of all active users with their current open ticket counts."""
        # Subquery: count open tickets per assignee
        open_counts = (
            select(
                Ticket.assignee_id.label("user_id"),
                func.count(Ticket.id).label("open_count"),
            )
            .where(Ticket.status.in_(_OPEN_STATUSES))
            .where(Ticket.assignee_id.isnot(None))
            .group_by(Ticket.assignee_id)
            .subquery()
        )

        stmt = (
            select(
                User.id,
                User.email,
                User.full_name,
                func.coalesce(open_counts.c.open_count, 0).label("open_count"),
            )
            .outerjoin(open_counts, User.id == open_counts.c.user_id)
            .where(User.is_active.is_(True))
            .order_by(func.coalesce(open_counts.c.open_count, 0).asc())
        )

        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "user_id": str(row.id),
                "email": row.email,
                "full_name": row.full_name,
                "open_count": row.open_count,
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Best-assignee selection
    # ------------------------------------------------------------------

    async def find_best_assignee(self, ticket: Ticket) -> User | None:
        """
        Select the best available agent for the given ticket.

        Strategy:
        1. If ticket has a department, prefer agents whose branch contact_email
           or (future) specialization matches — currently approximated by selecting
           active users with matching branch when ticket has a branch.
        2. Among candidates, pick lowest open-ticket count.
        3. Fall back to any active user with lowest open-ticket count.
        """
        # Subquery for open ticket counts
        open_counts = (
            select(
                Ticket.assignee_id.label("user_id"),
                func.count(Ticket.id).label("open_count"),
            )
            .where(Ticket.status.in_(_OPEN_STATUSES))
            .where(Ticket.assignee_id.isnot(None))
            .group_by(Ticket.assignee_id)
            .subquery()
        )

        def _candidates(roles: tuple[str, ...]):
            # Only people who can actually work a ticket are eligible. Without
            # a role filter the lowest-workload user is usually an auditor or
            # a branch user — both have zero open tickets precisely because
            # their roles cannot be assigned work, so they would win every
            # time and the ticket would land where it can never be actioned.
            return (
                select(User)
                .join(Role, Role.id == User.role_id)
                .outerjoin(open_counts, User.id == open_counts.c.user_id)
                .where(User.is_active.is_(True), Role.name.in_(roles))
                .order_by(func.coalesce(open_counts.c.open_count, 0).asc())
            )

        # Agents are tried before supervisors, and only then by workload.
        # Ranking purely on workload sends everything to whoever is idlest,
        # which is reliably a supervisor — they carry no queue of their own,
        # so frontline work would skip the agents entirely and pile onto the
        # people meant to be overseeing it.
        for roles, tier in (((AGENT_ROLE,), "agent"), (ASSIGNABLE_ROLES, "any")):
            stmt = _candidates(roles)

            if ticket.branch_id is not None:
                branch_match = (await self.db.execute(
                    stmt.where(User.branch_id == ticket.branch_id).limit(1)
                )).scalar_one_or_none()
                if branch_match:
                    log.info(
                        "routing.branch_match",
                        ticket_id=str(ticket.id),
                        assignee_id=str(branch_match.id),
                        branch_id=str(ticket.branch_id),
                        tier=tier,
                    )
                    return branch_match

            candidate = (await self.db.execute(stmt.limit(1))).scalar_one_or_none()
            if candidate:
                log.info(
                    "routing.workload_match",
                    ticket_id=str(ticket.id),
                    assignee_id=str(candidate.id),
                    tier=tier,
                )
                return candidate

        log.warning("routing.no_candidates", ticket_id=str(ticket.id))
        return None

    # ------------------------------------------------------------------
    # Auto-route
    # ------------------------------------------------------------------

    async def auto_route_ticket(self, ticket: Ticket) -> tuple[User | None, str]:
        """
        Find the best assignee, assign the ticket, and return (assignee, reason).

        The caller is responsible for committing the session.
        """
        assignee = await self.find_best_assignee(ticket)

        if assignee is None:
            log.warning("routing.no_agent_available", ticket_id=str(ticket.id))
            return None, "No available agent found; ticket left unassigned."

        reason = (
            f"Auto-routed to {assignee.full_name} ({assignee.email}) "
            f"based on current workload and branch matching."
        )

        ticket.assignee_id = assignee.id
        # Transition to ASSIGNED if in a pre-assignment state
        current_status = ticket.status if isinstance(ticket.status, str) else ticket.status.value
        if current_status in (TicketStatus.NEW.value, TicketStatus.ACKNOWLEDGED.value):
            ticket.status = TicketStatus.ASSIGNED.value

        await self.db.flush()
        log.info(
            "routing.auto_routed",
            ticket_id=str(ticket.id),
            assignee_id=str(assignee.id),
            reason=reason,
        )
        return assignee, reason

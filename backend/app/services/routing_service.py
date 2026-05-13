"""Routing service — intelligent ticket assignment based on workload and specialization.

Algorithm (in priority order):
1. Match agents whose branch/department aligns with the ticket's category/department.
2. Among those, pick the one with the fewest currently open tickets.
3. If no specialization match, fall back to any active agent by lowest open-ticket count.
4. If no agent is available, return None.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User

log = get_logger(__name__)

# Statuses that count toward an agent's active workload
_OPEN_STATUSES = {
    TicketStatus.NEW.value,
    TicketStatus.ACKNOWLEDGED.value,
    TicketStatus.ASSIGNED.value,
    TicketStatus.IN_PROGRESS.value,
    TicketStatus.ESCALATED.value,
    TicketStatus.REOPENED.value,
}


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

        base_stmt = (
            select(User)
            .outerjoin(open_counts, User.id == open_counts.c.user_id)
            .where(User.is_active.is_(True))
            .order_by(func.coalesce(open_counts.c.open_count, 0).asc())
        )

        # Attempt branch-matched assignment first
        if ticket.branch_id is not None:
            branch_stmt = base_stmt.where(User.branch_id == ticket.branch_id)
            candidate = (await self.db.execute(branch_stmt.limit(1))).scalar_one_or_none()
            if candidate:
                log.info(
                    "routing.branch_match",
                    ticket_id=str(ticket.id),
                    assignee_id=str(candidate.id),
                    branch_id=str(ticket.branch_id),
                )
                return candidate

        # Global fallback: lowest workload among all active users
        candidate = (await self.db.execute(base_stmt.limit(1))).scalar_one_or_none()
        if candidate:
            log.info(
                "routing.global_fallback",
                ticket_id=str(ticket.id),
                assignee_id=str(candidate.id),
            )
        return candidate

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

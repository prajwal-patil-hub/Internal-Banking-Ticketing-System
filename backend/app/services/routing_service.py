"""Routing service — who should work this ticket.

Order of preference:

1. A category rule, if one names somebody for this ticket's category.
2. Someone in the ticket's own branch, by lightest open queue.
3. Anyone assignable, by lightest open queue.

Agents are considered before supervisors at every step, and anyone on leave is
excluded throughout. Each step falls through rather than failing: a rule that
names someone on leave is skipped, not obeyed, because parking tickets on an
absent person is worse than having no rule at all.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.logging import get_logger
from app.models.assignment import AssignmentRule
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


def is_on_leave(user: User, on_date: date | None = None) -> bool:
    """Is this person inside a leave window on the given day?

    Both ends are inclusive, and either may be open: a `leave_from` with no
    `leave_to` is indefinite leave, and a `leave_to` with no `leave_from` is
    leave that has always been running and ends on that date. Neither set
    means available.
    """
    if user.leave_from is None and user.leave_to is None:
        return False
    today = on_date or date.today()
    if user.leave_from is not None and today < user.leave_from:
        return False
    return not (user.leave_to is not None and today > user.leave_to)


def _available_on(today: date):
    """SQL for "not on leave today" — the direct negation of `is_on_leave`.

    Someone is available when they have no leave recorded at all, or their
    leave has not started yet, or it has already ended.

    Expressed in SQL rather than filtered afterwards in Python so that the
    lowest-workload ordering applies to the people who can actually take the
    work. Ordering first and discarding the unavailable would return nobody
    whenever the idlest agent happened to be away.
    """
    return or_(
        and_(User.leave_from.is_(None), User.leave_to.is_(None)),
        and_(User.leave_from.isnot(None), User.leave_from > today),
        and_(User.leave_to.isnot(None), User.leave_to < today),
    )



class RoutingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Workload query
    # ------------------------------------------------------------------

    async def get_agent_workload(self) -> list[dict]:
        """Everyone who can be assigned work, with open counts and leave state.

        This backs the assign control, so it deliberately still lists people
        who are on leave rather than hiding them — a supervisor may knowingly
        assign to someone returning tomorrow. It marks them instead, and
        auto-routing skips them.
        """
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

        today = date.today()
        stmt = (
            select(
                User.id,
                User.email,
                User.full_name,
                Role.name.label("role"),
                User.leave_from,
                User.leave_to,
                User.leave_note,
                func.coalesce(open_counts.c.open_count, 0).label("open_count"),
            )
            .join(Role, Role.id == User.role_id)
            .outerjoin(open_counts, User.id == open_counts.c.user_id)
            # Only roles that can hold a ticket. Listing branch users and
            # auditors here would put people in the assign dropdown who cannot
            # action what they are given.
            .where(User.is_active.is_(True), Role.name.in_(ASSIGNABLE_ROLES))
            .order_by(func.coalesce(open_counts.c.open_count, 0).asc())
        )

        rows = (await self.db.execute(stmt)).all()
        out = []
        for row in rows:
            on_leave = not (
                (row.leave_from is None and row.leave_to is None)
                or (row.leave_from is not None and row.leave_from > today)
                or (row.leave_to is not None and row.leave_to < today)
            )
            out.append({
                "user_id": str(row.id),
                "email": row.email,
                "full_name": row.full_name,
                "role": row.role,
                "open_count": row.open_count,
                "on_leave": on_leave,
                "leave_from": row.leave_from.isoformat() if row.leave_from else None,
                "leave_to": row.leave_to.isoformat() if row.leave_to else None,
                "leave_note": row.leave_note,
            })
        return out

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

        today = date.today()

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
                .where(
                    User.is_active.is_(True),
                    Role.name.in_(roles),
                    _available_on(today),
                )
                .order_by(func.coalesce(open_counts.c.open_count, 0).asc())
            )

        # --- 1. a category rule, if one applies and the person can take it ---
        if ticket.category_id is not None:
            rule = (await self.db.execute(
                select(AssignmentRule).where(AssignmentRule.category_id == ticket.category_id)
            )).scalar_one_or_none()
            if rule is not None:
                named = (await self.db.execute(
                    select(User)
                    .join(Role, Role.id == User.role_id)
                    .where(
                        User.id == rule.assignee_id,
                        User.is_active.is_(True),
                        Role.name.in_(ASSIGNABLE_ROLES),
                        _available_on(today),
                    )
                )).scalar_one_or_none()
                if named is not None:
                    log.info(
                        "routing.category_rule",
                        ticket_id=str(ticket.id),
                        assignee_id=str(named.id),
                        category_id=str(ticket.category_id),
                    )
                    return named
                # Deliberately not an error. The rule names who *should* own
                # this category; when they are away the ticket still has to go
                # somewhere, so fall through to the ordinary search.
                log.info(
                    "routing.category_rule_unavailable",
                    ticket_id=str(ticket.id),
                    rule_assignee_id=str(rule.assignee_id),
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
        # Transition to ASSIGNED if in a pre-assignment state.
        #
        # The isinstance dance that used to be here existed because other code
        # assigned `TicketStatus.X.value` — a bare string — to this column, so
        # an in-session ticket could hold either type. Those all assign the
        # enum now, and `TicketStatus` subclasses `str`, so a plain comparison
        # is correct either way.
        if ticket.status in (TicketStatus.NEW, TicketStatus.ACKNOWLEDGED):
            ticket.status = TicketStatus.ASSIGNED

        await self.db.flush()
        log.info(
            "routing.auto_routed",
            ticket_id=str(ticket.id),
            assignee_id=str(assignee.id),
            reason=reason,
        )
        return assignee, reason

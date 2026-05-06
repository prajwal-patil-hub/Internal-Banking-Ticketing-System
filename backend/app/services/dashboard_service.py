"""Dashboard aggregator — single round trip, role-aware payload.

Avoids the per-tile fan-out the frontend used in P2. Returns:
  - counters relevant to the actor's role
  - recent rows that the actor is permitted to see
"""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role
from app.models.escalation import Escalation
from app.models.sla import SLATracking
from app.models.ticket import Ticket
from app.models.user import User

OPEN_STATUSES = (
    "new", "acknowledged", "assigned", "in_progress",
    "on_hold", "escalated", "reopened",
)


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def kpis(self, actor: User) -> dict:
        scope = self._branch_scope(actor)

        async def _count(*clauses) -> int:
            stmt = select(func.count()).select_from(Ticket)
            all_clauses = list(scope) + list(clauses)
            if all_clauses:
                stmt = stmt.where(and_(*all_clauses))
            return (await self.db.execute(stmt)).scalar_one()

        open_count = await _count(Ticket.status.in_(OPEN_STATUSES))
        critical_open = await _count(
            Ticket.status.in_(OPEN_STATUSES), Ticket.priority == "critical"
        )
        resolved_or_closed = await _count(Ticket.status.in_(("resolved", "closed")))

        # SLA breached count needs a join to sla_tracking unless we just
        # use Ticket.sla_due_at. Use the ticket clock for parity with the
        # filter chip on /tickets.
        breached_stmt = (
            select(func.count())
            .select_from(Ticket)
            .where(
                and_(
                    *scope,
                    Ticket.sla_due_at.is_not(None),
                    Ticket.sla_due_at < func.now(),
                    Ticket.status.notin_(("resolved", "closed")),
                )
            )
        )
        breached = (await self.db.execute(breached_stmt)).scalar_one()

        # Open escalations (unresolved). Visible to admin/supervisor only.
        open_escalations = 0
        if actor.role.name in {Role.ADMIN.value, Role.SUPERVISOR.value}:
            stmt = select(func.count()).select_from(Escalation).where(
                Escalation.resolved_at.is_(None)
            )
            open_escalations = (await self.db.execute(stmt)).scalar_one()

        sla_health = self._compute_health(open_count, breached)

        return {
            "open": open_count,
            "breached": breached,
            "critical_open": critical_open,
            "resolved": resolved_or_closed,
            "open_escalations": open_escalations,
            "sla_health": sla_health,  # 0..100
            "role": actor.role.name,
        }

    async def recent(self, actor: User, *, limit: int = 8) -> list[dict]:
        scope = self._branch_scope(actor)
        stmt = select(Ticket).order_by(Ticket.created_at.desc()).limit(limit)
        if scope:
            stmt = stmt.where(and_(*scope))
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            {
                "id": str(r.id),
                "ticket_no": r.ticket_no,
                "title": r.title,
                "status": r.status,
                "priority": r.priority,
                "sla_due_at": r.sla_due_at.isoformat() if r.sla_due_at else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    async def role_specific(self, actor: User) -> dict:
        """Extra panels per role, computed server-side."""
        role = actor.role.name
        if role == Role.ADMIN.value:
            unassigned = (
                await self.db.execute(
                    select(func.count()).select_from(Ticket).where(
                        Ticket.assigned_user_id.is_(None),
                        Ticket.status.in_(("new", "acknowledged")),
                    )
                )
            ).scalar_one()
            return {"unassigned_admin_queue": unassigned}

        if role == Role.AGENT.value:
            mine_open = (
                await self.db.execute(
                    select(func.count()).select_from(Ticket).where(
                        Ticket.assigned_user_id == actor.id,
                        Ticket.status.in_(OPEN_STATUSES),
                    )
                )
            ).scalar_one()
            return {"my_open": mine_open}

        if role == Role.SUPERVISOR.value:
            top_breaches = (
                await self.db.execute(
                    select(func.count()).select_from(SLATracking).where(
                        SLATracking.breached.is_(True),
                        SLATracking.policy_priority == "critical",
                    )
                )
            ).scalar_one()
            return {"critical_breaches": top_breaches}

        if role == Role.BRANCH_USER.value:
            my_tickets = (
                await self.db.execute(
                    select(func.count()).select_from(Ticket).where(
                        Ticket.raised_by == actor.id,
                        Ticket.status.in_(OPEN_STATUSES),
                    )
                )
            ).scalar_one()
            return {"my_open": my_tickets}

        return {}

    def _branch_scope(self, actor: User) -> list:
        if actor.role.name == Role.BRANCH_USER.value and actor.branch_id is not None:
            return [Ticket.branch_id == actor.branch_id]
        return []

    def _compute_health(self, open_count: int, breached: int) -> int:
        if open_count == 0:
            return 100
        return max(0, round(100 * (1 - breached / open_count)))

"""Dashboard aggregator — single round trip, role-aware payload.

Avoids the per-tile fan-out the frontend used in P2. Returns:
  - counters relevant to the actor's role
  - recent rows that the actor is permitted to see
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Float, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role
from app.models.branch import Branch
from app.models.category import Category
from app.models.escalation import Escalation
from app.models.sla import SLATracking
from app.models.ticket import Ticket
from app.models.user import User
from app.repositories.sla_repo import SLATrackingRepository

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

        # First-response SLA breach count (banks track this separately).
        response_breached = await SLATrackingRepository(self.db).count_response_breached()

        return {
            "open": open_count,
            "breached": breached,
            "response_breached": response_breached,
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

    # ────────────────────────── Analytics ──────────────────────────

    async def analytics(self, actor: User) -> dict:
        """Premium analytics payload — by status, priority, category,
        daily volume (last 14 days), top branches, and avg resolution
        time by priority. Branch-scoped for branch_user."""
        scope = self._branch_scope(actor)

        # By status (all)
        by_status_stmt = (
            select(Ticket.status, func.count())
            .group_by(Ticket.status)
        )
        if scope:
            by_status_stmt = by_status_stmt.where(and_(*scope))
        by_status_rows = (await self.db.execute(by_status_stmt)).all()
        by_status = {s: int(c) for (s, c) in by_status_rows}

        # By priority (open only)
        by_prio_stmt = (
            select(Ticket.priority, func.count())
            .where(Ticket.status.in_(OPEN_STATUSES))
            .group_by(Ticket.priority)
        )
        if scope:
            by_prio_stmt = by_prio_stmt.where(and_(*scope))
        by_prio_rows = (await self.db.execute(by_prio_stmt)).all()
        by_priority = {p: int(c) for (p, c) in by_prio_rows}

        # By category — return name, count, open_count
        by_cat_stmt = (
            select(
                Category.name,
                func.count(Ticket.id),
                func.sum(
                    func.case((Ticket.status.in_(OPEN_STATUSES), 1), else_=0)
                ).label("open_count"),
            )
            .join(Category, Category.id == Ticket.category_id, isouter=True)
            .group_by(Category.name)
            .order_by(func.count(Ticket.id).desc())
        )
        if scope:
            by_cat_stmt = by_cat_stmt.where(and_(*scope))
        by_cat_rows = (await self.db.execute(by_cat_stmt)).all()
        by_category = [
            {"name": (n or "(uncategorized)"), "total": int(t), "open": int(o or 0)}
            for (n, t, o) in by_cat_rows
        ]

        # Daily volume last 14 days
        now = datetime.now(UTC)
        start = (now - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_expr = func.date_trunc("day", Ticket.created_at).label("day")
        daily_stmt = (
            select(
                day_expr,
                func.count(),
                func.sum(
                    func.case(
                        (Ticket.priority == "critical", 1), else_=0,
                    )
                ),
            )
            .where(Ticket.created_at >= start)
            .group_by(day_expr)
            .order_by(day_expr)
        )
        if scope:
            daily_stmt = daily_stmt.where(and_(*scope))
        daily_rows = (await self.db.execute(daily_stmt)).all()
        # Build a contiguous series, zero-filling missing days
        by_day: dict[str, tuple[int, int]] = {
            (d.date().isoformat() if hasattr(d, 'date') else str(d)[:10]): (int(c), int(cr or 0))
            for (d, c, cr) in daily_rows
        }
        daily_volume: list[dict] = []
        for i in range(14):
            day = (start + timedelta(days=i)).date().isoformat()
            total, critical = by_day.get(day, (0, 0))
            daily_volume.append({"date": day, "total": total, "critical": critical})

        # Top branches by volume in last 30 days
        top_branches: list[dict] = []
        if not scope:
            since = now - timedelta(days=30)
            tb_stmt = (
                select(Branch.code, Branch.name, func.count(Ticket.id))
                .join(Ticket, Ticket.branch_id == Branch.id)
                .where(Ticket.created_at >= since)
                .group_by(Branch.code, Branch.name)
                .order_by(func.count(Ticket.id).desc())
                .limit(5)
            )
            tb_rows = (await self.db.execute(tb_stmt)).all()
            top_branches = [
                {"code": code, "name": name, "count": int(count)}
                for (code, name, count) in tb_rows
            ]

        # Average resolution minutes by priority (last 30 days)
        since = now - timedelta(days=30)
        avg_res_stmt = (
            select(
                Ticket.priority,
                func.avg(
                    cast(
                        (func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 60.0),
                        Float,
                    )
                ),
                func.count(),
            )
            .where(
                Ticket.resolved_at.is_not(None),
                Ticket.resolved_at >= since,
            )
            .group_by(Ticket.priority)
        )
        if scope:
            avg_res_stmt = avg_res_stmt.where(and_(*scope))
        avg_res_rows = (await self.db.execute(avg_res_stmt)).all()
        avg_resolution_minutes = [
            {"priority": p, "minutes": round(float(m), 1) if m is not None else None, "n": int(c)}
            for (p, m, c) in avg_res_rows
        ]

        return {
            "by_status": by_status,
            "by_priority": by_priority,
            "by_category": by_category,
            "daily_volume": daily_volume,
            "top_branches": top_branches,
            "avg_resolution_minutes": avg_resolution_minutes,
        }

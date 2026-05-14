"""Dashboard API routes.

Provides KPIs, SLA health, category distribution, department workload,
recent tickets, and AI system performance metrics.

All queries use SQLAlchemy async and respect role-based visibility.
Agents/admins/supervisors see all data. Branch users see branch-scoped data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.logging import get_logger
from app.models.ai_interaction import AIInteractionLog
from app.models.audit import AuditLog
from app.models.sla import SLATracking
from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.models.user import User
from app.schemas.envelope import ok

log = get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_BRANCH_USER_ROLE = "branch_user"


def _branch_filter(user: User):
    """Return a WHERE clause for branch-user scoping, or None for admins/agents."""
    if user.role.name == _BRANCH_USER_ROLE:
        return Ticket.reporter_id == user.id
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "/kpis",
    summary="Get key performance indicators",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_kpis(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    # Base ticket query (no branch filter for admins/agents)
    base = select(Ticket)
    access_filter = _branch_filter(current_user)
    if access_filter is not None:
        base = base.where(access_filter)

    # Total open tickets
    open_statuses = [
        TicketStatus.NEW, TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED, TicketStatus.REOPENED,
    ]
    total_open_stmt = select(func.count(Ticket.id)).where(Ticket.status.in_(open_statuses))
    total_open = (await db.execute(total_open_stmt)).scalar_one()

    # Tickets created today
    today_stmt = select(func.count(Ticket.id)).where(Ticket.created_at >= today_start)
    today_count = (await db.execute(today_stmt)).scalar_one()

    # Tickets created this week
    week_stmt = select(func.count(Ticket.id)).where(Ticket.created_at >= week_start)
    week_count = (await db.execute(week_stmt)).scalar_one()

    # SLA breached count (open tickets)
    breached_stmt = select(func.count(Ticket.id)).where(
        Ticket.sla_breached == True,  # noqa: E712
        Ticket.status.in_(open_statuses),
    )
    breached_count = (await db.execute(breached_stmt)).scalar_one()

    # Resolved today
    resolved_today_stmt = select(func.count(Ticket.id)).where(
        Ticket.status == TicketStatus.RESOLVED,
        Ticket.resolved_at >= today_start,
    )
    resolved_today = (await db.execute(resolved_today_stmt)).scalar_one()

    # Critical/high open tickets
    critical_high_stmt = select(func.count(Ticket.id)).where(
        Ticket.status.in_(open_statuses),
        Ticket.priority.in_([TicketPriority.CRITICAL, TicketPriority.HIGH]),
    )
    critical_high_count = (await db.execute(critical_high_stmt)).scalar_one()

    # Average resolution time (hours) for tickets resolved in last 30 days
    thirty_days_ago = now - timedelta(days=30)
    avg_resolution_stmt = select(
        func.avg(
            func.extract(
                "epoch",
                Ticket.resolved_at - Ticket.created_at,
            ) / 3600
        )
    ).where(
        Ticket.resolved_at >= thirty_days_ago,
        Ticket.resolved_at.is_not(None),
    )
    avg_resolution_hours = (await db.execute(avg_resolution_stmt)).scalar_one()

    # Unassigned tickets
    unassigned_stmt = select(func.count(Ticket.id)).where(
        Ticket.assignee_id.is_(None),
        Ticket.status.in_(open_statuses),
    )
    unassigned_count = (await db.execute(unassigned_stmt)).scalar_one()

    # Priority breakdown for open tickets
    priority_breakdown_stmt = select(
        Ticket.priority,
        func.count(Ticket.id).label("count"),
    ).where(Ticket.status.in_(open_statuses)).group_by(Ticket.priority)
    priority_result = await db.execute(priority_breakdown_stmt)
    priority_breakdown = {row.priority.value: row.count for row in priority_result}

    return ok({
        "total_open_tickets": total_open,
        "tickets_created_today": today_count,
        "tickets_created_this_week": week_count,
        "sla_breached_open": breached_count,
        "resolved_today": resolved_today,
        "critical_high_open": critical_high_count,
        "unassigned_open": unassigned_count,
        "avg_resolution_hours_30d": round(float(avg_resolution_hours or 0), 2),
        "priority_breakdown": priority_breakdown,
        "as_of": now.isoformat(),
    })


@router.get(
    "/sla-status",
    summary="Get SLA health data",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_sla_status(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    now = datetime.now(timezone.utc)
    open_statuses = [
        TicketStatus.NEW, TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED, TicketStatus.REOPENED,
    ]

    # Total open tracked
    total_tracked_stmt = select(func.count(SLATracking.id)).join(
        Ticket, SLATracking.ticket_id == Ticket.id
    ).where(Ticket.status.in_(open_statuses))
    total_tracked = (await db.execute(total_tracked_stmt)).scalar_one()

    # Response SLA: already breached
    response_breached_stmt = select(func.count(SLATracking.id)).join(
        Ticket, SLATracking.ticket_id == Ticket.id
    ).where(
        Ticket.status.in_(open_statuses),
        SLATracking.is_response_breached == True,  # noqa: E712
    )
    response_breached = (await db.execute(response_breached_stmt)).scalar_one()

    # Resolution SLA: already breached
    resolution_breached_stmt = select(func.count(SLATracking.id)).join(
        Ticket, SLATracking.ticket_id == Ticket.id
    ).where(
        Ticket.status.in_(open_statuses),
        SLATracking.is_resolution_breached == True,  # noqa: E712
    )
    resolution_breached = (await db.execute(resolution_breached_stmt)).scalar_one()

    # At-risk: resolution due within next 60 minutes and not breached
    at_risk_cutoff = now + timedelta(minutes=60)
    at_risk_stmt = select(func.count(SLATracking.id)).join(
        Ticket, SLATracking.ticket_id == Ticket.id
    ).where(
        Ticket.status.in_(open_statuses),
        SLATracking.is_resolution_breached == False,  # noqa: E712
        SLATracking.resolution_due_at <= at_risk_cutoff,
        SLATracking.resolution_due_at > now,
    )
    at_risk = (await db.execute(at_risk_stmt)).scalar_one()

    # SLA health by priority
    health_by_priority_stmt = select(
        Ticket.priority,
        func.count(Ticket.id).label("total"),
        func.sum(case((SLATracking.is_resolution_breached == True, 1), else_=0)).label("breached"),  # noqa: E712
    ).join(SLATracking, Ticket.id == SLATracking.ticket_id).where(
        Ticket.status.in_(open_statuses)
    ).group_by(Ticket.priority)

    health_result = await db.execute(health_by_priority_stmt)
    health_by_priority = {}
    for row in health_result:
        total_p = row.total or 0
        breached_p = int(row.breached or 0)
        health_by_priority[row.priority.value] = {
            "total": total_p,
            "breached": breached_p,
            "compliance_rate": round((1 - breached_p / total_p) * 100, 1) if total_p else 100.0,
        }

    in_compliance = total_tracked - resolution_breached
    sla_compliance_rate = round((in_compliance / total_tracked) * 100, 1) if total_tracked else 100.0

    return ok({
        "total_tracked": total_tracked,
        "response_sla_breached": response_breached,
        "resolution_sla_breached": resolution_breached,
        "at_risk_next_60min": at_risk,
        "sla_compliance_rate": sla_compliance_rate,
        "health_by_priority": health_by_priority,
        "as_of": now.isoformat(),
    })


@router.get(
    "/category-distribution",
    summary="Ticket distribution by category",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_category_distribution(
    request: Request,
    days: int = 30,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    if days < 1 or days > 365:
        days = 30

    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(
            TicketCategory.id,
            TicketCategory.name,
            TicketCategory.code,
            TicketCategory.department,
            func.count(Ticket.id).label("ticket_count"),
            func.sum(case((Ticket.status == TicketStatus.RESOLVED, 1), else_=0)).label("resolved"),
            func.sum(case((Ticket.sla_breached == True, 1), else_=0)).label("sla_breached"),  # noqa: E712
        )
        .outerjoin(Ticket, Ticket.category_id == TicketCategory.id)
        .where(
            TicketCategory.is_active == True,  # noqa: E712
        )
        .filter(
            (Ticket.created_at >= since) | (Ticket.id.is_(None))
        )
        .group_by(TicketCategory.id, TicketCategory.name, TicketCategory.code, TicketCategory.department)
        .order_by(func.count(Ticket.id).desc())
    )

    result = await db.execute(stmt)
    rows = result.fetchall()

    distribution = []
    for row in rows:
        count = row.ticket_count or 0
        resolved_count = int(row.resolved or 0)
        sla_br = int(row.sla_breached or 0)
        distribution.append({
            "category_id": str(row.id),
            "category_name": row.name,
            "category_code": row.code,
            "department": row.department,
            "ticket_count": count,
            "resolved_count": resolved_count,
            "sla_breach_count": sla_br,
            "resolution_rate": round((resolved_count / count) * 100, 1) if count else 0.0,
        })

    total_tickets = sum(r["ticket_count"] for r in distribution)

    return ok({
        "period_days": days,
        "total_tickets": total_tickets,
        "distribution": distribution,
    })


@router.get(
    "/department-load",
    summary="Workload by department",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_department_load(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    open_statuses = [
        TicketStatus.NEW, TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED, TicketStatus.REOPENED,
    ]

    # Department load from ticket.department field
    stmt = (
        select(
            Ticket.department,
            func.count(Ticket.id).label("open_tickets"),
            func.sum(case((Ticket.sla_breached == True, 1), else_=0)).label("sla_breached"),  # noqa: E712
            func.sum(case((Ticket.priority == TicketPriority.CRITICAL, 1), else_=0)).label("critical"),
            func.sum(case((Ticket.priority == TicketPriority.HIGH, 1), else_=0)).label("high"),
        )
        .where(
            Ticket.status.in_(open_statuses),
            Ticket.department.is_not(None),
        )
        .group_by(Ticket.department)
        .order_by(func.count(Ticket.id).desc())
    )

    result = await db.execute(stmt)
    rows = result.fetchall()

    department_load = [
        {
            "department": row.department,
            "open_tickets": row.open_tickets or 0,
            "sla_breached": int(row.sla_breached or 0),
            "critical_tickets": int(row.critical or 0),
            "high_tickets": int(row.high or 0),
        }
        for row in rows
    ]

    # Also load by category department mapping
    category_dept_stmt = (
        select(
            TicketCategory.department,
            func.count(Ticket.id).label("open_tickets"),
        )
        .join(Ticket, Ticket.category_id == TicketCategory.id)
        .where(Ticket.status.in_(open_statuses), Ticket.department.is_(None))
        .group_by(TicketCategory.department)
    )
    cat_result = await db.execute(category_dept_stmt)
    for row in cat_result.fetchall():
        existing = next((d for d in department_load if d["department"] == row.department), None)
        if existing:
            existing["open_tickets"] += row.open_tickets
        else:
            department_load.append({
                "department": row.department,
                "open_tickets": row.open_tickets or 0,
                "sla_breached": 0,
                "critical_tickets": 0,
                "high_tickets": 0,
            })

    return ok({
        "department_load": sorted(department_load, key=lambda x: x["open_tickets"], reverse=True),
        "as_of": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/recent-tickets", summary="10 most recent tickets (role-filtered)")
async def get_recent_tickets(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    stmt = select(Ticket)

    access_filter = _branch_filter(current_user)
    if access_filter is not None:
        stmt = stmt.where(access_filter)

    stmt = stmt.order_by(Ticket.created_at.desc()).limit(10)
    result = await db.execute(stmt)
    tickets = result.scalars().all()

    def _serialize_summary(t: Ticket) -> dict:
        return {
            "id": str(t.id),
            "ticket_number": t.ticket_number,
            "title": t.title,
            "status": t.status.value,
            "priority": t.priority.value,
            "reporter_id": str(t.reporter_id),
            "assignee_id": str(t.assignee_id) if t.assignee_id else None,
            "sla_breached": t.sla_breached,
            "category": t.category.name if t.category else None,
            "created_at": t.created_at.isoformat(),
        }

    return ok([_serialize_summary(t) for t in tickets])


@router.get(
    "/ai-metrics",
    summary="AI system performance metrics",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_ai_metrics(
    request: Request,
    days: int = 7,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    if days < 1 or days > 90:
        days = 7

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Total AI interactions
    total_stmt = select(func.count(AIInteractionLog.id)).where(
        AIInteractionLog.created_at >= since
    )
    total = (await db.execute(total_stmt)).scalar_one()

    # Success rate
    success_stmt = select(func.count(AIInteractionLog.id)).where(
        AIInteractionLog.created_at >= since,
        AIInteractionLog.success == True,  # noqa: E712
    )
    success_count = (await db.execute(success_stmt)).scalar_one()

    # By interaction type
    by_type_stmt = select(
        AIInteractionLog.interaction_type,
        func.count(AIInteractionLog.id).label("count"),
        func.avg(AIInteractionLog.latency_ms).label("avg_latency_ms"),
        func.sum(AIInteractionLog.prompt_tokens).label("total_input_tokens"),
        func.sum(AIInteractionLog.completion_tokens).label("total_output_tokens"),
        func.avg(AIInteractionLog.confidence_score).label("avg_confidence"),
    ).where(
        AIInteractionLog.created_at >= since
    ).group_by(AIInteractionLog.interaction_type)

    type_result = await db.execute(by_type_stmt)
    by_type = {}
    total_input_tokens = 0
    total_output_tokens = 0
    for row in type_result:
        in_tok = int(row.total_input_tokens or 0)
        out_tok = int(row.total_output_tokens or 0)
        total_input_tokens += in_tok
        total_output_tokens += out_tok
        by_type[row.interaction_type] = {
            "count": row.count,
            "avg_latency_ms": round(float(row.avg_latency_ms or 0), 0),
            "total_input_tokens": in_tok,
            "total_output_tokens": out_tok,
            "avg_confidence": round(float(row.avg_confidence or 0), 3) if row.avg_confidence else None,
        }

    # Average latency overall
    avg_latency_stmt = select(func.avg(AIInteractionLog.latency_ms)).where(
        AIInteractionLog.created_at >= since,
        AIInteractionLog.latency_ms.is_not(None),
    )
    avg_latency = (await db.execute(avg_latency_stmt)).scalar_one()

    return ok({
        "period_days": days,
        "total_interactions": total,
        "successful_interactions": success_count,
        "success_rate": round((success_count / total) * 100, 1) if total else 0.0,
        "avg_latency_ms": round(float(avg_latency or 0), 0),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "by_interaction_type": by_type,
        "as_of": datetime.now(timezone.utc).isoformat(),
    })

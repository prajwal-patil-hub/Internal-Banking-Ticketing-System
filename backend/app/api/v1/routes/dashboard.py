"""Dashboard API routes — returns data shaped exactly to frontend contract.

Endpoints and response shapes are locked to the frontend KPIData, SLAStatus,
CategoryItem, DeptLoad, and AIMetrics TypeScript interfaces.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.logging import get_logger
from app.models.ai_interaction import AIInteractionLog
from app.models.sla import SLATracking
from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketSource, TicketStatus
from app.models.user import User
from app.schemas.envelope import ok

log = get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_OPEN_STATUSES = [
    TicketStatus.NEW, TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED,
    TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED, TicketStatus.REOPENED,
]


def _branch_filter(user: User):
    if user.role.name == "branch_user":
        return Ticket.reporter_id == user.id
    return None


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

@router.get(
    "/kpis",
    summary="Key performance indicators",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_kpis(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    # Open tickets
    open_count = (await db.execute(
        select(func.count(Ticket.id)).where(Ticket.status.in_(_OPEN_STATUSES))
    )).scalar_one()

    # SLA breached (open)
    sla_breached_count = (await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.sla_breached == True,  # noqa: E712
            Ticket.status.in_(_OPEN_STATUSES),
        )
    )).scalar_one()

    # Resolved today
    resolved_today = (await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.status == TicketStatus.RESOLVED,
            Ticket.resolved_at >= today_start,
        )
    )).scalar_one()

    # Average resolution hours (last 30 days)
    avg_res_stmt = select(
        func.avg(
            func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600
        )
    ).where(
        Ticket.resolved_at >= thirty_days_ago,
        Ticket.resolved_at.is_not(None),
    )
    avg_resolution_hours = (await db.execute(avg_res_stmt)).scalar_one() or 0

    # Critical open tickets
    critical_open = (await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.status.in_(_OPEN_STATUSES),
            Ticket.priority == TicketPriority.CRITICAL,
        )
    )).scalar_one()

    # AI auto-categorized (have ai_category set, last 7 days)
    ai_auto_categorized = (await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.ai_category.is_not(None),
            Ticket.created_at >= now - timedelta(days=7),
        )
    )).scalar_one()

    # Email tickets created today
    email_tickets_today = (await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.source == TicketSource.EMAIL,
            Ticket.created_at >= today_start,
        )
    )).scalar_one()

    # Active escalations
    escalations_active = (await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.status == TicketStatus.ESCALATED,
        )
    )).scalar_one()

    return ok({
        "open_tickets":        open_count,
        "sla_breached":        sla_breached_count,
        "resolved_today":      resolved_today,
        "avg_resolution_hours": round(float(avg_resolution_hours), 2),
        "critical_open":       critical_open,
        "ai_auto_categorized": ai_auto_categorized,
        "email_tickets_today": email_tickets_today,
        "escalations_active":  escalations_active,
    })


# ---------------------------------------------------------------------------
# SLA Health
# ---------------------------------------------------------------------------

@router.get(
    "/sla-status",
    summary="SLA health summary",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_sla_status(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    now = datetime.now(UTC)
    at_risk_cutoff = now + timedelta(minutes=60)

    # Resolution-breached open tickets
    breached_count = (await db.execute(
        select(func.count(SLATracking.id))
        .join(Ticket, SLATracking.ticket_id == Ticket.id)
        .where(
            Ticket.status.in_(_OPEN_STATUSES),
            SLATracking.is_resolution_breached == True,  # noqa: E712
        )
    )).scalar_one()

    # At-risk: due within 60 min, not yet breached
    at_risk_count = (await db.execute(
        select(func.count(SLATracking.id))
        .join(Ticket, SLATracking.ticket_id == Ticket.id)
        .where(
            Ticket.status.in_(_OPEN_STATUSES),
            SLATracking.is_resolution_breached == False,  # noqa: E712
            SLATracking.resolution_due_at <= at_risk_cutoff,
            SLATracking.resolution_due_at > now,
        )
    )).scalar_one()

    # Total tracked open tickets
    total_tracked = (await db.execute(
        select(func.count(SLATracking.id))
        .join(Ticket, SLATracking.ticket_id == Ticket.id)
        .where(Ticket.status.in_(_OPEN_STATUSES))
    )).scalar_one()

    on_time = max(total_tracked - at_risk_count - breached_count, 0)
    compliance_rate = round((on_time / total_tracked) * 100, 1) if total_tracked else 100.0

    return ok({
        "on_time":        on_time,
        "at_risk":        at_risk_count,
        "breached":       breached_count,
        "compliance_rate": compliance_rate,
    })


# ---------------------------------------------------------------------------
# Category Distribution
# ---------------------------------------------------------------------------

@router.get(
    "/category-distribution",
    summary="Ticket count by category",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_category_distribution(
    request: Request,
    days: int = 30,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))

    stmt = (
        select(
            TicketCategory.name,
            func.count(Ticket.id).label("ticket_count"),
        )
        .outerjoin(Ticket, Ticket.category_id == TicketCategory.id)
        .where(
            TicketCategory.is_active == True,  # noqa: E712
            (Ticket.created_at >= since) | (Ticket.id.is_(None)),
        )
        .group_by(TicketCategory.name)
        .order_by(func.count(Ticket.id).desc())
    )

    rows = (await db.execute(stmt)).fetchall()
    total = sum(r.ticket_count or 0 for r in rows)

    distribution = [
        {
            "category":   row.name,
            "count":      row.ticket_count or 0,
            "percentage": round(((row.ticket_count or 0) / total) * 100, 1) if total else 0.0,
        }
        for row in rows
    ]

    return ok(distribution)


# ---------------------------------------------------------------------------
# Department Load
# ---------------------------------------------------------------------------

@router.get(
    "/department-load",
    summary="Open ticket load by department",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_department_load(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    now = datetime.now(UTC)

    stmt = (
        select(
            Ticket.department,
            func.count(Ticket.id).label("open_count"),
            func.sum(
                case((Ticket.sla_breached == True, 1), else_=0)  # noqa: E712
            ).label("breached_count"),
            func.avg(
                func.extract("epoch", now - Ticket.created_at) / 3600
            ).label("avg_age_hours"),
        )
        .where(
            Ticket.status.in_(_OPEN_STATUSES),
            Ticket.department.is_not(None),
        )
        .group_by(Ticket.department)
        .order_by(func.count(Ticket.id).desc())
    )

    rows = (await db.execute(stmt)).fetchall()

    department_load = [
        {
            "department":    row.department,
            "open_count":    row.open_count or 0,
            "breached_count": int(row.breached_count or 0),
            "avg_age_hours": round(float(row.avg_age_hours or 0), 1),
        }
        for row in rows
    ]

    return ok(department_load)


# ---------------------------------------------------------------------------
# Recent Tickets
# ---------------------------------------------------------------------------

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
    tickets = (await db.execute(stmt)).scalars().all()

    def _serialize(t: Ticket) -> dict:
        return {
            "id":            str(t.id),
            "ticket_number": t.ticket_number,
            "title":         t.title,
            "status":        t.status.value,
            "priority":      t.priority.value,
            "source":        t.source.value,
            "reporter_id":   str(t.reporter_id),
            "assignee_id":   str(t.assignee_id) if t.assignee_id else None,
            "sla_breached":  t.sla_breached,
            "ai_risk_score": t.ai_risk_score,
            "created_at":    t.created_at.isoformat(),
        }

    return ok([_serialize(t) for t in tickets])


# ---------------------------------------------------------------------------
# AI Metrics
# ---------------------------------------------------------------------------

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
    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 90)))

    # Total categorize interactions
    total_categorized = (await db.execute(
        select(func.count(AIInteractionLog.id)).where(
            AIInteractionLog.created_at >= since,
            AIInteractionLog.interaction_type == "categorize",
        )
    )).scalar_one()

    # Average confidence from categorize interactions
    avg_confidence_raw = (await db.execute(
        select(func.avg(AIInteractionLog.confidence_score)).where(
            AIInteractionLog.created_at >= since,
            AIInteractionLog.interaction_type == "categorize",
            AIInteractionLog.confidence_score.is_not(None),
        )
    )).scalar_one()

    # High-risk open tickets
    high_risk_tickets = (await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.status.in_(_OPEN_STATUSES),
            Ticket.ai_risk_score >= 0.7,
        )
    )).scalar_one()

    # Average latency across all AI calls in period
    avg_latency_raw = (await db.execute(
        select(func.avg(AIInteractionLog.latency_ms)).where(
            AIInteractionLog.created_at >= since,
            AIInteractionLog.latency_ms.is_not(None),
        )
    )).scalar_one()

    return ok({
        "total_categorized": total_categorized,
        "avg_confidence":    round(float(avg_confidence_raw or 0), 3),
        "high_risk_tickets": high_risk_tickets,
        "auto_resolved":     0,
        "avg_latency_ms":    round(float(avg_latency_raw or 0), 0),
    })

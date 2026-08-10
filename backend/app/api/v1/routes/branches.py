"""Branch management API.

`/branches` previously redirected to the org hierarchy, which is a different
thing: org units are the reporting tree, branches are physical places with
staff, a manager and a service state. This exposes the branch network with the
numbers that make it operationally useful — how much work each one is carrying
and how much of that is already late.

Ticket counts are computed here rather than stored on the row. Denormalising
them would mean every ticket transition has to remember to adjust a branch
counter, and the first missed update leaves a number that is wrong forever with
nothing to reveal it.
"""

from __future__ import annotations

import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.branch import Branch, BranchStatus
from app.models.ticket import OPEN_STATUSES, Ticket
from app.models.user import User
from app.schemas.envelope import ok

log = get_logger(__name__)

router = APIRouter(prefix="/branches", tags=["branches"])


def _serialize(branch: Branch, stats: dict | None = None) -> dict:
    stats = stats or {}
    open_count = stats.get("open_tickets", 0)
    capacity = branch.ticket_capacity or 0
    return {
        "id": str(branch.id),
        "code": branch.code,
        "name": branch.name,
        "region": branch.region,
        "address": branch.address,
        "ifsc": branch.ifsc,
        "contact_email": branch.contact_email,
        "contact_phone": branch.contact_phone,
        "is_active": branch.is_active,
        "status": branch.status.value,
        "status_note": branch.status_note,
        "manager_id": str(branch.manager_id) if branch.manager_id else None,
        "manager": (
            {"id": str(branch.manager.id), "full_name": branch.manager.full_name}
            if branch.manager else None
        ),
        "ticket_capacity": capacity,
        "open_tickets": open_count,
        "breached_tickets": stats.get("breached_tickets", 0),
        # Percent of capacity in use. Capped for display so a badly
        # under-provisioned branch renders as a full bar rather than
        # overflowing its container.
        "load_percent": min(round((open_count / capacity) * 100), 100) if capacity else 0,
        "created_at": branch.created_at.isoformat(),
    }


async def _ticket_stats(db: AsyncSession) -> dict[uuid.UUID, dict]:
    """Open and breached ticket counts per branch, in one query."""
    rows = (await db.execute(
        select(
            Ticket.branch_id,
            func.count(Ticket.id).label("open_tickets"),
            func.sum(
                case((Ticket.sla_breached.is_(True), 1), else_=0)
            ).label("breached_tickets"),
        )
        .where(Ticket.branch_id.is_not(None), Ticket.status.in_(OPEN_STATUSES))
        .group_by(Ticket.branch_id)
    )).all()
    return {
        row.branch_id: {
            "open_tickets": row.open_tickets or 0,
            "breached_tickets": int(row.breached_tickets or 0),
        }
        for row in rows
    }


@router.get("", summary="List branches with live load")
async def list_branches(
    request: Request,
    region: Annotated[str | None, Query()] = None,
    branch_status: Annotated[str | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    stmt = select(Branch).order_by(Branch.name)

    if region:
        stmt = stmt.where(Branch.region == region)
    if branch_status:
        try:
            stmt = stmt.where(Branch.status == BranchStatus(branch_status))
        except ValueError:
            raise ValidationError(
                f"Invalid status: {branch_status}. Expected one of: "
                f"{', '.join(s.value for s in BranchStatus)}"
            )
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Branch.name).like(pattern) | func.lower(Branch.code).like(pattern)
        )

    branches = (await db.execute(stmt)).scalars().all()
    stats = await _ticket_stats(db)
    return ok([_serialize(b, stats.get(b.id)) for b in branches])


@router.get("/summary", summary="Branch network health")
async def branch_summary(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Counts by service state, plus the regions present.

    Uptime is the share of branches currently operational — a headline the
    network view can lead with rather than making the reader tally the table.
    """
    rows = (await db.execute(
        select(Branch.status, func.count()).group_by(Branch.status)
    )).all()
    counts = {s.value: 0 for s in BranchStatus}
    for row_status, count in rows:
        counts[row_status.value] = count

    total = sum(counts.values())
    regions = [
        r for (r,) in (await db.execute(
            select(Branch.region).where(Branch.region != "").distinct().order_by(Branch.region)
        )).all()
    ]

    return ok({
        "total": total,
        "operational": counts["operational"],
        "maintenance": counts["maintenance"],
        "incident": counts["incident"],
        "uptime_percent": round((counts["operational"] / total) * 100, 1) if total else 100.0,
        "regions": regions,
    })


@router.get("/export", summary="Download the branch list as CSV")
async def export_branches(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "supervisor")),
) -> Response:
    branches = (await db.execute(select(Branch).order_by(Branch.name))).scalars().all()
    stats = await _ticket_stats(db)

    columns = [
        "code", "name", "region", "status", "manager", "open_tickets",
        "breached_tickets", "ticket_capacity", "load_percent", "ifsc",
        "contact_email", "contact_phone",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for branch in branches:
        row = _serialize(branch, stats.get(branch.id))
        row["manager"] = row["manager"]["full_name"] if row["manager"] else ""
        writer.writerow(row)

    return Response(
        content=buf.getvalue().encode(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="branches.csv"'},
    )


@router.get("/{branch_id}", summary="Get one branch")
async def get_branch(
    branch_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise NotFoundError(f"Branch {branch_id} not found.")
    stats = await _ticket_stats(db)
    return ok(_serialize(branch, stats.get(branch.id)))


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a branch (admin)")
async def create_branch(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin")),
) -> dict:
    code = str(payload.get("code", "")).strip().upper()
    name = str(payload.get("name", "")).strip()
    if not code or not name:
        raise ValidationError("code and name are required.")

    existing = (await db.execute(select(Branch.id).where(Branch.code == code))).scalar_one_or_none()
    if existing:
        raise ConflictError(f"A branch with code '{code}' already exists.")

    branch = Branch(
        id=uuid.uuid4(),
        code=code,
        name=name,
        region=str(payload.get("region", "")).strip(),
        address=str(payload.get("address", "")).strip(),
        ifsc=str(payload.get("ifsc", "")).strip().upper(),
        contact_email=str(payload.get("contact_email", "")).strip(),
        contact_phone=str(payload.get("contact_phone", "")).strip(),
        status=BranchStatus(payload.get("status", "operational")),
        status_note=str(payload.get("status_note", "")).strip(),
        ticket_capacity=int(payload.get("ticket_capacity", 20)),
        is_active=bool(payload.get("is_active", True)),
    )
    if manager_id := payload.get("manager_id"):
        branch.manager_id = uuid.UUID(str(manager_id))

    db.add(branch)
    await db.commit()
    await db.refresh(branch)

    log.info("branch_created", branch_id=str(branch.id), code=code, actor=str(current_user.id))
    return ok(_serialize(branch))


@router.patch("/{branch_id}", summary="Update a branch (admin)")
async def update_branch(
    branch_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin")),
) -> dict:
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise NotFoundError(f"Branch {branch_id} not found.")

    for field in ("name", "region", "address", "ifsc", "contact_email",
                  "contact_phone", "status_note"):
        if field in payload:
            setattr(branch, field, str(payload[field]).strip())

    if "status" in payload:
        try:
            branch.status = BranchStatus(payload["status"])
        except ValueError:
            raise ValidationError(f"Invalid status: {payload['status']}")

    if "ticket_capacity" in payload:
        capacity = int(payload["ticket_capacity"])
        if capacity < 1:
            raise ValidationError("ticket_capacity must be at least 1.")
        branch.ticket_capacity = capacity

    if "is_active" in payload:
        branch.is_active = bool(payload["is_active"])

    if "manager_id" in payload:
        branch.manager_id = (
            uuid.UUID(str(payload["manager_id"])) if payload["manager_id"] else None
        )

    await db.commit()
    await db.refresh(branch)

    log.info("branch_updated", branch_id=str(branch.id), actor=str(current_user.id))
    stats = await _ticket_stats(db)
    return ok(_serialize(branch, stats.get(branch.id)))


@router.delete("/{branch_id}", summary="Deactivate a branch (admin)")
async def deactivate_branch(
    branch_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin")),
) -> Response:
    """Soft delete. Tickets and users reference branches, so a hard delete
    would either fail on the FK or orphan history."""
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise NotFoundError(f"Branch {branch_id} not found.")

    branch.is_active = False
    await db.commit()
    log.info("branch_deactivated", branch_id=str(branch_id), actor=str(current_user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

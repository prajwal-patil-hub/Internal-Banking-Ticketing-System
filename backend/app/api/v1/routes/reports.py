"""Report download endpoints: CSV, Excel, PDF."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.models.user import User
from app.services.report_service import (
    generate_analytics_excel,
    generate_analytics_pdf,
    generate_csv,
    generate_excel,
    generate_pdf,
)

log = get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])

_FORMATS = {"csv", "xlsx", "pdf"}


@router.get("/tickets", summary="Download ticket audit report")
async def download_ticket_report(
    format: Annotated[str, Query(description="csv | xlsx | pdf")] = "csv",
    from_date: Annotated[str | None, Query()] = None,
    to_date: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    priority: Annotated[str | None, Query()] = None,
    org_unit_id: Annotated[uuid.UUID | None, Query()] = None,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    if format not in _FORMATS:
        raise ValidationError(f"format must be one of: {', '.join(sorted(_FORMATS))}")

    filters: dict = {}
    if from_date:
        try:
            filters["from_date"] = datetime.fromisoformat(from_date)
        except ValueError:
            raise ValidationError("from_date must be ISO 8601 format.")
    if to_date:
        try:
            filters["to_date"] = datetime.fromisoformat(to_date)
        except ValueError:
            raise ValidationError("to_date must be ISO 8601 format.")
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    if org_unit_id:
        filters["org_unit_id"] = org_unit_id

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"ticket_report_{timestamp}"

    if format == "csv":
        content = await generate_csv(db, filters, current_user)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )
    elif format == "xlsx":
        content = await generate_excel(db, filters, current_user)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
        )
    else:  # pdf
        content = await generate_pdf(db, filters, current_user)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        )


_ANALYTICS_FORMATS = {"xlsx", "pdf"}


@router.post("/analytics", summary="Export dashboard charts and KPIs as PDF or Excel")
async def export_analytics(
    payload: dict,
    format: Annotated[str, Query(description="xlsx | pdf")] = "pdf",
    current_user: User = Depends(get_current_user),
) -> Response:
    """Render already-computed dashboard data into a document.

    The client sends what it is displaying — KPI tiles, each chart's rows, and
    optionally the chart's rendered PNG — rather than the server recomputing
    it. That keeps the export byte-for-byte consistent with the screen the user
    is looking at, including any filters they applied, and it avoids adding a
    PDF or spreadsheet library to the frontend bundle.

    No org filtering is applied here because nothing is read from the database:
    the payload can only contain data the caller was already authorised to see.
    """
    if format not in _ANALYTICS_FORMATS:
        raise ValidationError(
            f"format must be one of: {', '.join(sorted(_ANALYTICS_FORMATS))}"
        )

    charts = payload.get("charts") or []
    kpis = payload.get("kpis") or []
    if not charts and not kpis:
        raise ValidationError("Nothing to export — provide charts or kpis.")

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    base = str(payload.get("filename") or "dashboard").strip() or "dashboard"
    # Keep the filename header safe regardless of what the client sent.
    base = "".join(ch for ch in base if ch.isalnum() or ch in "-_")[:60] or "dashboard"
    filename = f"{base}_{stamp}"

    if format == "xlsx":
        content = generate_analytics_excel(payload)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        content = generate_analytics_pdf(payload)
        media = "application/pdf"
        ext = "pdf"

    log.info(
        "analytics_exported",
        user_id=str(current_user.id),
        format=format,
        charts=len(charts),
        kpis=len(kpis),
    )
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}.{ext}"'},
    )

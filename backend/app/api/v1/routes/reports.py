"""Report download endpoints: CSV, Excel, PDF."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session
from app.core.exceptions import ValidationError
from app.models.user import User
from app.services.report_service import generate_csv, generate_excel, generate_pdf

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

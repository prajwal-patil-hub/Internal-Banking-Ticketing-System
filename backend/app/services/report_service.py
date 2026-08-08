"""Report generation service: CSV, Excel (.xlsx), PDF with comprehensive audit fields."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketStatus
from app.models.user import User
from app.services.org_service import get_hierarchy_chain


REPORT_COLUMNS = [
    "ticket_id",
    "ticket_number",
    "title",
    "status",
    "priority",
    "source",
    "org_unit_code",
    "org_unit_name",
    "org_level",
    "hierarchy_chain",
    "raised_by_email",
    "raised_by_name",
    "raised_at",
    "acknowledged_at",
    "first_response_at",
    "resolved_by_email",
    "resolved_by_name",
    "resolved_at",
    "closed_at",
    "sla_breached",
    "sla_due_at",
    "sla_response_due_at",
    "escalation_count",
    "escalation_time_hrs",
    "reopen_count",
    "ai_assisted",
    "ai_confidence",
    "category",
    "subcategory",
    "tags",
    "department",
    "internal_notes",
]


async def _build_report_rows(
    db: AsyncSession,
    filters: dict,
    current_user: User,
) -> list[dict[str, Any]]:
    """Fetch tickets with all audit fields and return as list of dicts."""
    from app.models.escalation import EscalationEvent
    from app.models.ai_interaction import AIInteractionLog
    from app.services.org_service import get_accessible_org_unit_ids

    stmt = select(Ticket)

    # Apply org visibility
    if not current_user.is_super_admin:
        if current_user.org_unit_id:
            accessible = await get_accessible_org_unit_ids(current_user, db)
            if accessible is not None:
                from sqlalchemy import or_
                stmt = stmt.where(
                    or_(
                        Ticket.org_unit_id.in_([str(uid) for uid in accessible]),
                        Ticket.assignee_id == current_user.id,
                    )
                )
        elif current_user.role.name == "branch_user":
            stmt = stmt.where(Ticket.reporter_id == current_user.id)

    # Apply date filters
    if filters.get("from_date"):
        stmt = stmt.where(Ticket.created_at >= filters["from_date"])
    if filters.get("to_date"):
        stmt = stmt.where(Ticket.created_at <= filters["to_date"])
    if filters.get("status"):
        try:
            stmt = stmt.where(Ticket.status == TicketStatus(filters["status"]))
        except ValueError:
            pass
    if filters.get("org_unit_id"):
        stmt = stmt.where(Ticket.org_unit_id == uuid.UUID(str(filters["org_unit_id"])))
    if filters.get("priority"):
        from app.models.ticket import TicketPriority
        try:
            stmt = stmt.where(Ticket.priority == TicketPriority(filters["priority"]))
        except ValueError:
            pass

    stmt = stmt.order_by(Ticket.created_at.desc())
    result = await db.execute(stmt)
    tickets = result.scalars().all()

    rows: list[dict[str, Any]] = []
    for ticket in tickets:
        # Escalation count and total time
        esc_result = await db.execute(
            select(func.count(EscalationEvent.id)).where(
                EscalationEvent.ticket_id == ticket.id
            )
        )
        esc_count = esc_result.scalar_one() or 0

        # Calculate escalation time (sum of durations between escalations)
        esc_time_hrs: float | None = None
        if esc_count > 0:
            esc_events_result = await db.execute(
                select(EscalationEvent.triggered_at, EscalationEvent.resolved_at).where(
                    EscalationEvent.ticket_id == ticket.id
                ).order_by(EscalationEvent.triggered_at)
            )
            esc_events = esc_events_result.all()
            total_esc_ms = 0.0
            for ev in esc_events:
                if ev.triggered_at and ev.resolved_at:
                    total_esc_ms += (ev.resolved_at - ev.triggered_at).total_seconds()
            esc_time_hrs = round(total_esc_ms / 3600, 2) if total_esc_ms else None

        # AI assisted check
        ai_result = await db.execute(
            select(func.count(AIInteractionLog.id)).where(
                AIInteractionLog.ticket_id == ticket.id
            )
        )
        ai_assisted = (ai_result.scalar_one() or 0) > 0 or bool(ticket.ai_category)

        # Hierarchy chain
        hierarchy_chain_str = ""
        if ticket.org_unit_id:
            chain = await get_hierarchy_chain(db, ticket.org_unit_id)
            hierarchy_chain_str = " > ".join(
                f"{c['name']} ({c['code']})" for c in chain
            )

        rows.append({
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "title": ticket.title,
            "status": ticket.status.value,
            "priority": ticket.priority.value,
            "source": ticket.source.value,
            "org_unit_code": ticket.org_unit.code if ticket.org_unit else "",
            "org_unit_name": ticket.org_unit.name if ticket.org_unit else "",
            "org_level": (
                ticket.org_unit.hierarchy_level.name
                if ticket.org_unit and ticket.org_unit.hierarchy_level
                else ""
            ),
            "hierarchy_chain": hierarchy_chain_str,
            "raised_by_email": ticket.reporter.email if ticket.reporter else "",
            "raised_by_name": ticket.reporter.full_name if ticket.reporter else "",
            "raised_at": ticket.created_at.isoformat() if ticket.created_at else "",
            "acknowledged_at": "",
            "first_response_at": ticket.first_response_at.isoformat() if ticket.first_response_at else "",
            "resolved_by_email": ticket.assignee.email if ticket.assignee else "",
            "resolved_by_name": ticket.assignee.full_name if ticket.assignee else "",
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else "",
            "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else "",
            "sla_breached": "Yes" if ticket.sla_breached else "No",
            "sla_due_at": ticket.resolution_due_at.isoformat() if ticket.resolution_due_at else "",
            "sla_response_due_at": ticket.response_due_at.isoformat() if ticket.response_due_at else "",
            "escalation_count": esc_count,
            "escalation_time_hrs": esc_time_hrs if esc_time_hrs is not None else "",
            "reopen_count": ticket.reopen_count or 0,
            "ai_assisted": "Yes" if ai_assisted else "No",
            "ai_confidence": round(ticket.ai_confidence * 100, 1) if ticket.ai_confidence else "",
            "category": ticket.category.name if ticket.category else "",
            "subcategory": ticket.subcategory.name if ticket.subcategory else "",
            "tags": ", ".join(ticket.tags or []),
            "department": ticket.department or "",
            "internal_notes": ticket.internal_notes or "",
        })

    return rows


async def generate_csv(db: AsyncSession, filters: dict, current_user: User) -> bytes:
    rows = await _build_report_rows(db, filters, current_user)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility


async def generate_excel(db: AsyncSession, filters: dict, current_user: User) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    rows = await _build_report_rows(db, filters, current_user)

    wb = Workbook()
    ws = wb.active
    ws.title = "Ticket Report"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1A5276")

    headers = [col.replace("_", " ").title() for col in REPORT_COLUMNS]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    for row_idx, row in enumerate(rows, start=2):
        for col_idx, col_key in enumerate(REPORT_COLUMNS, start=1):
            ws.cell(row=row_idx, column=col_idx, value=str(row.get(col_key, "")))

    # Auto-width (approximate)
    for col_idx in range(1, len(REPORT_COLUMNS) + 1):
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = 18

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def generate_pdf(db: AsyncSession, filters: dict, current_user: User) -> bytes:
    from reportlab.lib.pagesizes import landscape, A3
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    rows = await _build_report_rows(db, filters, current_user)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A3),
        leftMargin=1 * cm,
        rightMargin=1 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()

    story = [
        Paragraph("Ticket Audit Report", styles["Title"]),
        Paragraph(
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
            f"Total records: {len(rows)}",
            styles["Normal"],
        ),
        Spacer(1, 0.4 * cm),
    ]

    # Only show key columns in PDF (full list is too wide for a page)
    pdf_cols = [
        "ticket_number", "title", "status", "priority",
        "org_unit_code", "raised_by_name", "raised_at",
        "resolved_at", "sla_breached", "reopen_count",
        "escalation_count", "ai_assisted",
    ]
    headers = [[col.replace("_", " ").title() for col in pdf_cols]]
    data_rows = [
        [str(row.get(col, ""))[:40] for col in pdf_cols]
        for row in rows
    ]
    table_data = headers + data_rows

    col_widths = [3.5 * cm] * len(pdf_cols)
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A5276")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EBF5FB")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#AED6F1")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    doc.build(story)
    return buf.getvalue()

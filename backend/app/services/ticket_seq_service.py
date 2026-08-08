"""Atomic ticket sequence generation.

Format: {org_unit.code}{YY}{NNNNN}
  - org_unit.code: variable-length org code (e.g. "12345" for a branch)
  - YY: last 2 digits of current year
  - NNNNN: 5-digit zero-padded sequence, resets each year per org unit

Example: branch code "12345", year 2026, first ticket → "123452600001"
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org import OrgUnit, TicketSequence


async def generate_ticket_number(db: AsyncSession, org_unit_id: uuid.UUID) -> str:
    """Generate the next ticket number for the given org unit atomically."""
    now = datetime.now(timezone.utc)
    year_2d = now.year % 100

    # Fetch org unit for its code
    ou_result = await db.execute(select(OrgUnit).where(OrgUnit.id == org_unit_id))
    org_unit = ou_result.scalar_one_or_none()
    if org_unit is None:
        raise ValueError(f"OrgUnit {org_unit_id} not found")

    # Lock the sequence row for this org unit + year
    stmt = (
        select(TicketSequence)
        .where(
            TicketSequence.org_unit_id == org_unit_id,
            TicketSequence.year == now.year,
        )
        .with_for_update()
    )
    result = await db.execute(stmt)
    seq_row = result.scalar_one_or_none()

    if seq_row is None:
        seq_row = TicketSequence(
            org_unit_id=org_unit_id,
            year=now.year,
            last_seq=1,
        )
        db.add(seq_row)
        next_seq = 1
    else:
        seq_row.last_seq += 1
        next_seq = seq_row.last_seq

    return f"{org_unit.code}{year_2d:02d}{next_seq:05d}"


async def generate_ticket_number_legacy(db: AsyncSession) -> str:
    """Fallback ticket number for users without an org_unit (legacy format)."""
    from sqlalchemy import func
    from app.models.ticket import Ticket

    result = await db.execute(select(func.count(Ticket.id)))
    count = result.scalar_one() or 0
    return f"TKT-{count + 1:06d}"

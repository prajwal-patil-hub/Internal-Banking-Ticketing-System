"""Sequential ticket-number generator: TKT-YYYY-NNNNNN.

Backed by a Postgres sequence so concurrent inserts get unique numbers
without table locks.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SEQUENCE_NAME = "ticket_number_seq"


async def next_ticket_number(db: AsyncSession) -> str:
    row = await db.execute(text(f"SELECT nextval('{SEQUENCE_NAME}')"))
    n: int = row.scalar_one()
    year = datetime.now(UTC).year
    return f"TKT-{year}-{n:06d}"

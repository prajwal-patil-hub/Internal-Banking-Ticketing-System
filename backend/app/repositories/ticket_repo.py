"""Ticket data access — list with filters/pagination, get by id/no, create.

Filter support: status, priority, branch_id, assigned_user_id, breached
(SLA past due), free-text q (matches ticket_no, title), date range (created_at).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket


class TicketFilter:
    def __init__(
        self,
        *,
        status: Iterable[str] | None = None,
        priority: Iterable[str] | None = None,
        branch_id: uuid.UUID | None = None,
        assigned_user_id: uuid.UUID | None = None,
        breached: bool | None = None,
        q: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> None:
        self.status = list(status) if status else None
        self.priority = list(priority) if priority else None
        self.branch_id = branch_id
        self.assigned_user_id = assigned_user_id
        self.breached = breached
        self.q = q
        self.date_from = date_from
        self.date_to = date_to


class TicketRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _apply(self, stmt, f: TicketFilter, *, scoped_branch_id: uuid.UUID | None = None):
        clauses = []
        if scoped_branch_id is not None:
            clauses.append(Ticket.branch_id == scoped_branch_id)
        if f.status:
            clauses.append(Ticket.status.in_(f.status))
        if f.priority:
            clauses.append(Ticket.priority.in_(f.priority))
        if f.branch_id:
            clauses.append(Ticket.branch_id == f.branch_id)
        if f.assigned_user_id:
            clauses.append(Ticket.assigned_user_id == f.assigned_user_id)
        if f.breached is True:
            clauses.append(and_(Ticket.sla_due_at.is_not(None), Ticket.sla_due_at < func.now()))
        elif f.breached is False:
            clauses.append(or_(Ticket.sla_due_at.is_(None), Ticket.sla_due_at >= func.now()))
        if f.q:
            like = f"%{f.q.lower()}%"
            clauses.append(or_(func.lower(Ticket.ticket_no).like(like), func.lower(Ticket.title).like(like)))
        if f.date_from:
            clauses.append(Ticket.created_at >= f.date_from)
        if f.date_to:
            clauses.append(Ticket.created_at <= f.date_to)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        return stmt

    _SORTABLE = {
        "created_at": Ticket.created_at,
        "sla_due_at": Ticket.sla_due_at,
        "priority":   Ticket.priority,
        "status":     Ticket.status,
        "ticket_no":  Ticket.ticket_no,
    }

    async def list(
        self,
        *,
        f: TicketFilter,
        offset: int,
        limit: int,
        scoped_branch_id: uuid.UUID | None = None,
        sort: str | None = None,
    ) -> tuple[list[Ticket], int]:
        base = select(Ticket)
        count_stmt = self._apply(select(func.count()).select_from(Ticket), f, scoped_branch_id=scoped_branch_id)
        list_stmt = self._apply(base, f, scoped_branch_id=scoped_branch_id)

        # `sort` is a comma-or-leading-dash field like "-created_at" or
        # "priority,sla_due_at". Unknown fields are silently ignored.
        order_cols = []
        if sort:
            for part in (s.strip() for s in sort.split(",")):
                if not part:
                    continue
                descending = part.startswith("-")
                key = part.lstrip("-")
                col = self._SORTABLE.get(key)
                if col is None:
                    continue
                order_cols.append(col.desc() if descending else col.asc())
        if not order_cols:
            order_cols = [Ticket.created_at.desc()]
        list_stmt = list_stmt.order_by(*order_cols)

        total = (await self.db.execute(count_stmt)).scalar_one()
        rows = (await self.db.execute(list_stmt.offset(offset).limit(limit))).scalars().all()
        return list(rows), total

    async def get(self, tid: uuid.UUID) -> Ticket | None:
        return await self.db.get(Ticket, tid)

    async def get_by_no(self, ticket_no: str) -> Ticket | None:
        stmt = select(Ticket).where(Ticket.ticket_no == ticket_no)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create(self, t: Ticket) -> Ticket:
        self.db.add(t)
        await self.db.flush()
        return t

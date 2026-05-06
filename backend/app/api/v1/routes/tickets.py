"""Ticket endpoints — listing, retrieval, creation, workflow transitions,
comments, attachments, and assignment history.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage_adapter import StorageAdapter
from app.api.v1.deps import get_current_user, get_session, require_permissions
from app.core import idempotency
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.rbac import Role
from app.models.ticket_history import Attachment
from app.models.user import User
from app.repositories.ticket_history_repo import (
    AttachmentRepository,
    TicketAssignmentRepository,
    TicketCommentRepository,
)
from app.repositories.ticket_repo import TicketFilter
from app.schemas.envelope import ok, paginated
from app.schemas.ticket import TicketCreate, TicketPublic, TicketSummary
from app.schemas.workflow import (
    AssignmentPublic,
    AssignRequest,
    AttachmentPublic,
    CommentCreate,
    CommentPublic,
    EscalateRequest,
    ReopenRequest,
    ResolveRequest,
)
from app.services.ticket_service import TicketService
from app.services.workflow_service import WorkflowService
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/tickets", tags=["tickets"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIMES = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "application/pdf",
    "text/plain", "text/csv", "application/json",
    "application/zip", "application/x-zip-compressed",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ---- list / get / create -------------------------------------------------

@router.get("")
async def list_tickets(
    p: PageParams = Depends(page_params),
    status: list[str] | None = Query(default=None),
    priority: list[str] | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    assigned_user_id: uuid.UUID | None = Query(default=None),
    breached: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    f = TicketFilter(
        status=status, priority=priority, branch_id=branch_id,
        assigned_user_id=assigned_user_id, breached=breached, q=q,
        date_from=date_from, date_to=date_to,
    )
    items, total = await TicketService(db).list_for(user, f=f, offset=p.offset, limit=p.limit)
    return paginated(
        [TicketSummary.model_validate(t).model_dump(mode="json") for t in items],
        page=p.page, size=p.size, total=total,
    )


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    t = await TicketService(db).get_for(user, ticket_id)
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


@router.post("")
async def create_ticket(
    payload: TicketCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.create")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    # Idempotency: if the client retries with the same key we return the
    # cached response and do NOT create a duplicate ticket.
    actor_id = str(user.id)
    if idempotency_key:
        cached = await idempotency.lookup(actor_id, idempotency_key)
        if cached is not None:
            return cached
        if not await idempotency.reserve(actor_id, idempotency_key):
            # Another request with the same key is in flight.
            raise ConflictError("Duplicate request — retry shortly.")

    try:
        t = await TicketService(db).create(
            actor=user,
            branch_id=payload.branch_id,
            category_id=payload.category_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
        )
        await db.commit()
        response = ok(TicketPublic.model_validate(t).model_dump(mode="json"))
    except Exception:
        if idempotency_key:
            await idempotency.release(actor_id, idempotency_key)
        raise

    if idempotency_key:
        await idempotency.store(actor_id, idempotency_key, response)
    return response


def _csv_quote(v: object) -> str:
    s = "" if v is None else str(v)
    needs = any(c in s for c in (",", "\"", "\n", "\r"))
    if needs:
        return "\"" + s.replace("\"", "\"\"") + "\""
    return s


@router.get("/export.csv")
async def export_tickets_csv(
    status: list[str] | None = Query(default=None),
    priority: list[str] | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    assigned_user_id: uuid.UUID | None = Query(default=None),
    breached: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    f = TicketFilter(
        status=status, priority=priority, branch_id=branch_id,
        assigned_user_id=assigned_user_id, breached=breached, q=q,
        date_from=date_from, date_to=date_to,
    )
    items, _ = await TicketService(db).list_for(user, f=f, offset=0, limit=10_000)

    header = [
        "ticket_no", "title", "status", "priority", "branch_id",
        "raised_by", "assigned_user_id", "assigned_team_id",
        "sla_due_at", "first_response_at", "resolved_at", "closed_at",
        "reopened_count", "created_at",
    ]

    def gen():
        yield ",".join(header) + "\n"
        for t in items:
            row = [
                t.ticket_no, t.title, t.status, t.priority,
                t.branch_id, t.raised_by, t.assigned_user_id, t.assigned_team_id,
                t.sla_due_at.isoformat() if t.sla_due_at else "",
                t.first_response_at.isoformat() if t.first_response_at else "",
                t.resolved_at.isoformat() if t.resolved_at else "",
                t.closed_at.isoformat() if t.closed_at else "",
                t.reopened_count,
                t.created_at.isoformat(),
            ]
            yield ",".join(_csv_quote(c) for c in row) + "\n"

    return StreamingResponse(
        gen(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="tickets.csv"'},
    )


# ---- transitions ---------------------------------------------------------

@router.post("/{ticket_id}/acknowledge")
async def acknowledge(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.transition")),
) -> dict:
    t = await WorkflowService(db).acknowledge(user, ticket_id)
    await db.commit()
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


@router.post("/{ticket_id}/assign")
async def assign(
    ticket_id: uuid.UUID,
    payload: AssignRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.assign")),
) -> dict:
    t = await WorkflowService(db).assign(
        user, ticket_id,
        user_id=payload.user_id, team_id=payload.team_id, reason=payload.reason,
    )
    await db.commit()
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


@router.post("/{ticket_id}/start")
async def start(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.transition")),
) -> dict:
    t = await WorkflowService(db).start(user, ticket_id)
    await db.commit()
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


@router.post("/{ticket_id}/hold")
async def hold(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.transition")),
) -> dict:
    t = await WorkflowService(db).hold(user, ticket_id)
    await db.commit()
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


@router.post("/{ticket_id}/escalate")
async def escalate(
    ticket_id: uuid.UUID,
    payload: EscalateRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.escalate")),
) -> dict:
    t = await WorkflowService(db).escalate(user, ticket_id, reason=payload.reason)
    await db.commit()
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


@router.post("/{ticket_id}/resolve")
async def resolve(
    ticket_id: uuid.UUID,
    payload: ResolveRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.resolve")),
) -> dict:
    t = await WorkflowService(db).resolve(user, ticket_id, notes=payload.notes)
    await db.commit()
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


@router.post("/{ticket_id}/close")
async def close(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.close")),
) -> dict:
    t = await WorkflowService(db).close(user, ticket_id)
    await db.commit()
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


@router.post("/{ticket_id}/reopen")
async def reopen(
    ticket_id: uuid.UUID,
    payload: ReopenRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.reopen")),
) -> dict:
    t = await WorkflowService(db).reopen(user, ticket_id, reason=payload.reason)
    await db.commit()
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


# ---- comments ------------------------------------------------------------

@router.get("/{ticket_id}/comments")
async def list_comments(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    # Reuse get_for to enforce branch scoping for branch_user accounts.
    await TicketService(db).get_for(user, ticket_id)
    include_internal = user.role.name != Role.BRANCH_USER.value
    rows = await TicketCommentRepository(db).list_for(ticket_id, include_internal=include_internal)
    return ok([CommentPublic.model_validate(r).model_dump(mode="json") for r in rows])


@router.post("/{ticket_id}/comments")
async def add_comment(
    ticket_id: uuid.UUID,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.comment")),
) -> dict:
    if payload.is_internal:
        # Permission is implicitly granted via ticket.comment_internal; check it here
        # to give a precise error rather than a vague forbidden.
        from app.repositories.user_repo import RoleRepository
        granted = await RoleRepository(db).get_permission_codes(user.role_id)
        if "ticket.comment_internal" not in granted:
            raise ValidationError("You are not allowed to post internal comments.")
    c = await WorkflowService(db).add_comment(
        user, ticket_id, body=payload.body, is_internal=payload.is_internal
    )
    await db.commit()
    return ok(CommentPublic.model_validate(c).model_dump(mode="json"))


# ---- attachments ---------------------------------------------------------

@router.get("/{ticket_id}/attachments")
async def list_attachments(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    await TicketService(db).get_for(user, ticket_id)
    rows = await AttachmentRepository(db).list_for(ticket_id)
    return ok([AttachmentPublic.model_validate(r).model_dump(mode="json") for r in rows])


@router.post("/{ticket_id}/attachments")
async def upload_attachment(
    ticket_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.attach")),
) -> dict:
    await TicketService(db).get_for(user, ticket_id)

    if file.content_type not in ALLOWED_MIMES:
        raise ValidationError(
            "Unsupported attachment type.",
            details={"mime": file.content_type, "allowed": sorted(ALLOWED_MIMES)},
        )

    body = await file.read()
    if len(body) > MAX_UPLOAD_BYTES:
        raise ValidationError(
            "Attachment too large.",
            details={"max_bytes": MAX_UPLOAD_BYTES, "got_bytes": len(body)},
        )

    storage = StorageAdapter()
    storage.ensure_bucket()
    stored = storage.put_attachment(
        ticket_id=ticket_id,
        file_name=file.filename or "upload.bin",
        content_type=file.content_type or "application/octet-stream",
        body=body,
    )

    a = Attachment(
        ticket_id=ticket_id,
        uploaded_by=user.id,
        file_name=file.filename or "upload.bin",
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=stored.size_bytes,
        storage_key=stored.storage_key,
        checksum_sha256=stored.checksum_sha256,
    )
    await AttachmentRepository(db).add(a)
    await db.commit()
    return ok(AttachmentPublic.model_validate(a).model_dump(mode="json"))


@router.get("/{ticket_id}/attachments/{attachment_id}")
async def download_attachment(
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    await TicketService(db).get_for(user, ticket_id)
    a = await AttachmentRepository(db).get(attachment_id)
    if a is None or a.ticket_id != ticket_id:
        raise NotFoundError("Attachment not found.")
    # Streaming the bytes is straightforward; for now we expose the metadata
    # plus a presigned-url stub. Real signed URLs land in P8 when we tighten
    # storage IAM. For now we surface the storage_key so admins can resolve
    # via MinIO console if needed.
    return ok(AttachmentPublic.model_validate(a).model_dump(mode="json"))


# ---- assignment history --------------------------------------------------

@router.get("/{ticket_id}/assignments")
async def list_assignments(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    await TicketService(db).get_for(user, ticket_id)
    rows = await TicketAssignmentRepository(db).list_for(ticket_id)
    return ok([AssignmentPublic.model_validate(r).model_dump(mode="json") for r in rows])

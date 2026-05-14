"""Ticket-domain Pydantic v2 schemas.

Covers: categories, tickets (full and summary), comments, attachments,
and paginated list responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import TicketPriority, TicketSource, TicketStatus


# ---------------------------------------------------------------------------
# Category / SubCategory
# ---------------------------------------------------------------------------


class CategoryOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    department: str
    banking_domain: str
    description: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubCategoryOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    code: str
    name: str
    description: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Ticket CRUD
# ---------------------------------------------------------------------------


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")
    priority: TicketPriority = TicketPriority.MEDIUM
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    source: TicketSource = TicketSource.PORTAL
    tags: list[str] | None = None


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: TicketPriority | None = None
    status: TicketStatus | None = None
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    internal_notes: str | None = None
    tags: list[str] | None = None


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    reason: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Ticket output
# ---------------------------------------------------------------------------


class TicketOut(BaseModel):
    id: uuid.UUID
    ticket_number: str
    title: str
    description: str | None
    status: TicketStatus
    priority: TicketPriority
    source: TicketSource

    category_id: uuid.UUID | None
    subcategory_id: uuid.UUID | None
    reporter_id: uuid.UUID
    assignee_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    department: str | None
    tags: list[str] | None

    ai_category: str | None
    ai_subcategory: str | None
    ai_confidence: float | None
    ai_summary: str | None
    ai_risk_score: float | None
    ai_routing_reason: str | None
    ai_sentiment: str | None

    email_message_id: str | None
    email_from: str | None
    email_subject: str | None

    sla_policy_id: uuid.UUID | None
    response_due_at: datetime | None
    resolution_due_at: datetime | None
    sla_breached: bool
    sla_paused_at: datetime | None

    first_response_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None

    duplicate_of_id: uuid.UUID | None
    is_duplicate: bool
    internal_notes: str | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketSummary(BaseModel):
    id: uuid.UUID
    ticket_number: str
    title: str
    status: TicketStatus
    priority: TicketPriority
    source: TicketSource
    category_id: uuid.UUID | None
    reporter_id: uuid.UUID
    assignee_id: uuid.UUID | None
    created_at: datetime
    sla_breached: bool
    ai_confidence: float | None
    ai_risk_score: float | None

    model_config = ConfigDict(from_attributes=True)


class TicketListResponse(BaseModel):
    items: list[TicketSummary]
    total: int
    page: int
    per_page: int


# ---------------------------------------------------------------------------
# Comment
# ---------------------------------------------------------------------------


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    is_internal: bool = False


class CommentOut(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    is_internal: bool
    source: str
    ai_generated: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------


class AttachmentOut(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    has_pii_detected: bool
    is_clean: bool | None
    document_type: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

"""Ticket-related Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.ticket import TicketPriority, TicketSource, TicketStatus


# ---------------------------------------------------------------------------
# Category schemas
# ---------------------------------------------------------------------------

class SubCategoryOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CategoryOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    department: str
    banking_domain: str
    description: str
    is_active: bool
    created_at: datetime
    subcategories: list[SubCategoryOut] = []

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    code: str = Field(max_length=30)
    name: str = Field(max_length=100)
    department: str = Field(max_length=100)
    banking_domain: str = Field(max_length=50)
    description: str = Field(default="", max_length=255)
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    banking_domain: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class SubCategoryCreate(BaseModel):
    code: str = Field(max_length=30)
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=255)
    is_active: bool = True


# ---------------------------------------------------------------------------
# Ticket schemas
# ---------------------------------------------------------------------------

class TicketCreate(BaseModel):
    title: str = Field(max_length=255)
    description: str | None = None
    priority: TicketPriority = TicketPriority.MEDIUM
    source: TicketSource = TicketSource.PORTAL
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    department: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = None
    internal_notes: str | None = None


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    priority: TicketPriority | None = None
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    department: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = None
    internal_notes: str | None = None


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    reason: str | None = Field(default=None, max_length=500)


class TicketAssign(BaseModel):
    assignee_id: uuid.UUID


class TicketDuplicate(BaseModel):
    original_ticket_id: uuid.UUID


class UserBrief(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str

    model_config = {"from_attributes": True}


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
    ai_sentiment: str | None
    sla_breached: bool
    response_due_at: datetime | None
    resolution_due_at: datetime | None
    sla_paused_at: datetime | None
    first_response_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    is_duplicate: bool
    duplicate_of_id: uuid.UUID | None
    internal_notes: str | None
    created_at: datetime
    updated_at: datetime
    reporter: UserBrief | None = None
    assignee: UserBrief | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Comment schemas
# ---------------------------------------------------------------------------

class CommentCreate(BaseModel):
    body: str
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
    author: UserBrief | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# AI schemas
# ---------------------------------------------------------------------------

class AICategorizeResult(BaseModel):
    category: str | None
    subcategory: str | None
    confidence: float
    sentiment: str | None
    risk_score: float | None
    routing_reason: str | None


class AISummaryResult(BaseModel):
    summary: str
    key_points: list[str]


class AISuggestResult(BaseModel):
    suggestions: list[str]
    resolution_steps: list[str]
    estimated_complexity: str | None


# ---------------------------------------------------------------------------
# Chat schemas
# ---------------------------------------------------------------------------

class ChatMessageIn(BaseModel):
    content: str
    session_id: uuid.UUID | None = None
    ticket_id: uuid.UUID | None = None


class ChatMessageOut(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID
    content: str
    role: str
    created_at: datetime


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    title: str | None
    ticket_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    ended_at: datetime | None
    message_count: int = 0

    model_config = {"from_attributes": True}


class ChatSessionDetail(BaseModel):
    id: uuid.UUID
    title: str | None
    ticket_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    ended_at: datetime | None
    messages: list[dict[str, Any]] = []

    model_config = {"from_attributes": True}


class AIExtractEmailResult(BaseModel):
    title: str
    description: str
    priority: TicketPriority
    category_hint: str | None
    sender_name: str | None
    urgency_signals: list[str]


# ---------------------------------------------------------------------------
# Audit schemas
# ---------------------------------------------------------------------------

class AuditLogOut(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: str | None
    action: str
    actor_id: uuid.UUID | None
    actor_email: str | None
    actor_role: str | None
    old_values: dict | None
    new_values: dict | None
    ip_address: str | None
    request_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

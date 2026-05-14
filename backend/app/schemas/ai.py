"""AI-related Pydantic v2 schemas.

Covers: chat sessions/messages, AI categorization results, email extraction,
and resolution suggestions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatMessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None
    context_type: str | None = None   # e.g. "ticket", "general"
    context_id: str | None = None     # e.g. ticket UUID as string


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    tokens_used: int | None
    latency_ms: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    context_type: str | None
    context_id: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# AI results
# ---------------------------------------------------------------------------


class AICategorizationResult(BaseModel):
    category: str
    subcategory: str | None = None
    priority: str
    confidence: float
    risk_score: float
    risk_factors: list[str]
    department: str
    sla_recommendation: str
    routing_reason: str
    requires_escalation: bool
    is_regulatory: bool
    sentiment: str


class AIResolutionSuggestion(BaseModel):
    suggestion: str
    confidence: float
    similar_ticket_ids: list[str]
    knowledge_refs: list[str]


class AIEmailExtraction(BaseModel):
    title: str
    summary: str
    category: str
    priority: str
    confidence: float
    entities: dict[str, list[str]]   # account_refs, transaction_refs, urgency_signals
    risk_score: float

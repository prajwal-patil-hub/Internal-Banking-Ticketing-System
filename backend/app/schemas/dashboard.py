"""Dashboard and reporting Pydantic v2 schemas.

Covers: KPI aggregates, department load, category distribution, SLA status,
and the full dashboard response envelope.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.ticket import TicketSummary


# ---------------------------------------------------------------------------
# KPI / aggregation
# ---------------------------------------------------------------------------


class KPIData(BaseModel):
    open_tickets: int
    sla_breached: int
    resolved_today: int
    avg_resolution_hours: float
    critical_open: int
    ai_auto_categorized: int
    email_tickets_today: int
    escalations_active: int


class DepartmentLoad(BaseModel):
    department: str
    open_count: int
    breached_count: int
    avg_age_hours: float


class CategoryDistribution(BaseModel):
    category: str
    count: int
    percentage: float


class SLAStatus(BaseModel):
    on_time: int
    at_risk: int
    breached: int
    compliance_rate: float


# ---------------------------------------------------------------------------
# Dashboard aggregate
# ---------------------------------------------------------------------------


class DashboardData(BaseModel):
    kpis: KPIData
    department_load: list[DepartmentLoad]
    category_distribution: list[CategoryDistribution]
    sla_status: SLAStatus
    recent_tickets: list[TicketSummary]


# ---------------------------------------------------------------------------
# Audit log output
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

    model_config = ConfigDict(from_attributes=True)

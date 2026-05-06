"""Domain enums shared across models / schemas / services."""

from __future__ import annotations

from enum import StrEnum


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TicketStatus(StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


# Allowed transitions table (validated in service layer; not enforced by DB)
ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.NEW:          {TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED},
    TicketStatus.ACKNOWLEDGED: {TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS},
    TicketStatus.ASSIGNED:     {TicketStatus.IN_PROGRESS, TicketStatus.ON_HOLD, TicketStatus.ESCALATED},
    TicketStatus.IN_PROGRESS:  {TicketStatus.ON_HOLD, TicketStatus.ESCALATED, TicketStatus.RESOLVED},
    TicketStatus.ON_HOLD:      {TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED},
    TicketStatus.ESCALATED:    {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED},
    TicketStatus.RESOLVED:     {TicketStatus.CLOSED, TicketStatus.REOPENED},
    TicketStatus.CLOSED:       {TicketStatus.REOPENED},
    TicketStatus.REOPENED:     {TicketStatus.IN_PROGRESS, TicketStatus.ASSIGNED},
}

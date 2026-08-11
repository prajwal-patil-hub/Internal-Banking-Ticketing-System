"""Grounding for the AI assistant.

The assistant used to receive a fixed system prompt and nothing else — not the
ticket the user was looking at, not their queue, nothing. Asked about the
ticket on screen it had no way to know, so instead of saying so it produced a
generic essay on how one might analyse a ticket. Every token of that was
wasted, and a confident answer built on no data is worse than a refusal.

This module assembles a compact, factual CONTEXT block from the database and
hands it to the model, subject to three hard rules:

1. **Never widen access.** Context is fetched through the same visibility
   rules as the REST API. A branch user asking about someone else's ticket
   gets nothing, exactly as if they had opened the URL directly. The assistant
   must not become a way to read tickets you cannot otherwise read.
2. **Stay inside a budget.** Context is capped in characters. A local model
   re-reads the whole prompt on every turn, so unbounded context is a
   permanent latency and cost tax on the conversation.
3. **Prefer omission to truncation mid-fact.** Whole fields are dropped rather
   than cut in half, so the model never reads a mangled number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.config import settings
from app.core.logging import get_logger
from app.models.comment import TicketComment
from app.models.ticket import OPEN_STATUSES, Ticket
from app.models.user import User
from app.services.org_service import get_accessible_org_unit_ids

log = get_logger(__name__)


#: How many recent comments of the focused ticket to include.
MAX_COMMENTS = 5
#: Characters per comment before it is trimmed.
MAX_COMMENT_CHARS = 220
#: Characters of the ticket description before it is trimmed.
MAX_DESCRIPTION_CHARS = 700
#: Rows in the "your open work" list.
MAX_QUEUE_ROWS = 6


@dataclass
class ChatContext:
    """Rendered context plus what it is made of, for logging and the UI."""

    text: str
    #: Short labels describing each source, shown to the user so the widget can
    #: state what the assistant can actually see instead of implying more.
    sources: list[str] = field(default_factory=list)
    ticket_number: str | None = None
    #: True when the user pointed at a ticket they are not allowed to read.
    access_denied: bool = False


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC") if value else "—"


def _rel_hours(value: datetime | None, now: datetime) -> str:
    """'in 3h' / '4h ago' — models reason about deadlines better in relative terms."""
    if value is None:
        return "—"
    delta = (value - now).total_seconds() / 3600
    if abs(delta) < 1:
        mins = int(abs(delta) * 60)
        return f"in {mins}m" if delta >= 0 else f"{mins}m ago"
    return f"in {delta:.0f}h" if delta >= 0 else f"{abs(delta):.0f}h ago"


def _trim(text: str | None, limit: int) -> str:
    if not text:
        return "—"
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit].rstrip() + "…"


async def _visibility_clause(db: AsyncSession, user: User):
    """The same WHERE clause the ticket list endpoint applies.

    Kept deliberately close to `_ticket_access_filter` in the tickets route: if
    the two ever diverge, the assistant becomes a read-around for the ACL.
    """
    if user.is_super_admin:
        return None
    if user.org_unit_id:
        accessible = await get_accessible_org_unit_ids(user, db)
        if accessible is not None:
            return or_(
                Ticket.org_unit_id.in_(accessible),
                Ticket.assignee_id == user.id,
            )
        return None
    if authz.is_branch_user(user):
        return Ticket.reporter_id == user.id
    return None


async def _load_visible_ticket(
    db: AsyncSession, user: User, ticket_id: str
) -> Ticket | None:
    import uuid as _uuid

    try:
        parsed = _uuid.UUID(str(ticket_id))
    except (ValueError, AttributeError):
        return None

    stmt = select(Ticket).where(Ticket.id == parsed)
    if (clause := await _visibility_clause(db, user)) is not None:
        stmt = stmt.where(clause)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _render_ticket(db: AsyncSession, ticket: Ticket, now: datetime) -> str:
    lines = [
        "## The ticket currently open on screen",
        f"Number: {ticket.ticket_number}",
        f"Title: {ticket.title}",
        f"Status: {ticket.status.value} | Priority: {ticket.priority.value} | Source: {ticket.source.value}",
    ]

    if ticket.category:
        lines.append(f"Category: {ticket.category.name}")
    if ticket.department:
        lines.append(f"Department: {ticket.department}")

    reporter = ticket.reporter.full_name if ticket.reporter else "unknown"
    assignee = ticket.assignee.full_name if ticket.assignee else "unassigned"
    lines.append(f"Raised by: {reporter} | Assigned to: {assignee}")

    lines.append(f"Created: {_fmt_dt(ticket.created_at)}")
    sla = "BREACHED" if ticket.sla_breached else "within target"
    if ticket.sla_paused_at:
        sla = "paused"
    lines.append(
        f"SLA: {sla} | resolution due {_fmt_dt(ticket.resolution_due_at)} "
        f"({_rel_hours(ticket.resolution_due_at, now)})"
    )
    if ticket.reopen_count:
        lines.append(f"Reopened {ticket.reopen_count} time(s)")
    if ticket.tags:
        lines.append(f"Tags: {', '.join(ticket.tags)}")

    lines.append(f"Description: {_trim(ticket.description, MAX_DESCRIPTION_CHARS)}")

    if ticket.ai_summary:
        lines.append(f"Existing AI summary: {_trim(ticket.ai_summary, 300)}")
    if ticket.ai_risk_score is not None:
        lines.append(f"AI risk score: {ticket.ai_risk_score:.2f}")

    comments = (await db.execute(
        select(TicketComment)
        .where(TicketComment.ticket_id == ticket.id)
        .order_by(TicketComment.created_at.desc())
        .limit(MAX_COMMENTS)
    )).scalars().all()

    if comments:
        lines.append(f"Recent comments (newest last, {len(comments)} of the thread):")
        for comment in reversed(comments):
            author = comment.author.full_name if comment.author else "system"
            marker = "internal" if comment.is_internal else "public"
            lines.append(
                f"  - [{_fmt_dt(comment.created_at)}] {author} ({marker}): "
                f"{_trim(comment.body, MAX_COMMENT_CHARS)}"
            )

    return "\n".join(lines)


async def _render_workspace(db: AsyncSession, user: User, now: datetime) -> str:
    """A small digest of the user's own workload.

    Without this, ordinary questions like "what's breached?" or "what should I
    pick up next?" have nothing to stand on, and the model either refuses or
    invents. It is a handful of aggregates, so it costs very little.
    """
    clause = await _visibility_clause(db, user)

    def scoped(stmt):
        return stmt.where(clause) if clause is not None else stmt

    status_rows = (await db.execute(
        scoped(
            select(Ticket.status, func.count())
            .where(Ticket.status.in_(OPEN_STATUSES))
            .group_by(Ticket.status)
        )
    )).all()

    breached = (await db.execute(
        scoped(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.status.in_(OPEN_STATUSES), Ticket.sla_breached.is_(True))
        )
    )).scalar_one()

    lines = ["## Your workspace right now (only tickets you may see)"]
    if status_rows:
        counts = ", ".join(f"{s.value}: {c}" for s, c in sorted(status_rows, key=lambda r: r[0].value))
        lines.append(f"Open tickets by status — {counts}")
    else:
        lines.append("No open tickets are visible to you.")
    lines.append(f"Open tickets past their SLA: {breached}")

    mine = (await db.execute(
        select(Ticket)
        .where(Ticket.assignee_id == user.id, Ticket.status.in_(OPEN_STATUSES))
        .order_by(Ticket.sla_breached.desc(), Ticket.resolution_due_at.asc())
        .limit(MAX_QUEUE_ROWS)
    )).scalars().all()

    if mine:
        lines.append("Assigned to you (most urgent first):")
        for ticket in mine:
            flag = " [BREACHED]" if ticket.sla_breached else ""
            lines.append(
                f"  - {ticket.ticket_number} ({ticket.priority.value}, {ticket.status.value}){flag} "
                f"due {_rel_hours(ticket.resolution_due_at, now)} — {_trim(ticket.title, 80)}"
            )
    else:
        lines.append("Nothing is currently assigned to you.")

    return "\n".join(lines)


def _render_screen(page: dict) -> str:
    """What the user is looking at, as reported by the client."""
    route = str(page.get("route") or "").strip()
    label = str(page.get("label") or "").strip()
    if not route and not label:
        return ""

    lines = ["## The screen the user is on"]
    if label:
        lines.append(f"Page: {label}")
    if route:
        lines.append(f"Route: {route}")

    # Free-form key/value pairs the page chooses to expose (active filters,
    # selected tab, visible totals). Bounded so a client cannot inflate the
    # prompt, and stringified because values arrive as arbitrary JSON.
    details = page.get("details")
    if isinstance(details, dict) and details:
        rendered = [
            f"  - {str(k)[:40]}: {_trim(str(v), 120)}"
            for k, v in list(details.items())[:12]
        ]
        lines.append("Visible on this page:")
        lines.extend(rendered)

    return "\n".join(lines)


async def build_chat_context(
    db: AsyncSession,
    user: User,
    *,
    ticket_id: str | None = None,
    page: dict | None = None,
) -> ChatContext:
    """Assemble everything the assistant is allowed to know for this turn."""
    now = datetime.now(UTC)
    blocks: list[str] = []
    sources: list[str] = []
    ticket_number: str | None = None
    access_denied = False

    header = [
        "# CONTEXT",
        f"Current time: {_fmt_dt(now)}",
        f"You are talking to: {user.full_name} ({user.email}), role '{user.role.name}'"
        + (" with super admin rights" if user.is_super_admin else ""),
    ]
    blocks.append("\n".join(header))

    if ticket_id:
        ticket = await _load_visible_ticket(db, user, ticket_id)
        if ticket is not None:
            blocks.append(await _render_ticket(db, ticket, now))
            sources.append(f"ticket {ticket.ticket_number}")
            ticket_number = ticket.ticket_number
        else:
            # Say so in the context rather than staying silent: otherwise the
            # model treats the ticket as simply absent and starts guessing.
            access_denied = True
            blocks.append(
                "## The ticket currently open on screen\n"
                "Not available to you — it does not exist or your role cannot see it. "
                "Tell the user exactly that and do not speculate about its contents."
            )
            log.info(
                "chat_context.ticket_denied",
                user_id=str(user.id),
                role=user.role.name,
                ticket_id=str(ticket_id),
            )

    if page and (screen := _render_screen(page)):
        blocks.append(screen)
        sources.append("current page")

    blocks.append(await _render_workspace(db, user, now))
    sources.append("your ticket queue")

    text = "\n\n".join(b for b in blocks if b)

    # Final guard. Individual sections are already bounded, so hitting this
    # means something unexpected grew; drop the tail rather than ship a prompt
    # that blows the model's context window.
    limit = settings.AI_CONTEXT_CHAR_BUDGET
    if len(text) > limit:
        text = text[:limit].rstrip() + "\n…(context truncated)"
        log.warning("chat_context.truncated", user_id=str(user.id), chars=len(text))

    return ChatContext(
        text=text,
        sources=sources,
        ticket_number=ticket_number,
        access_denied=access_denied,
    )

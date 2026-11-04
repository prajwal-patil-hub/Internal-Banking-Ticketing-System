"""The AI helpers on a ticket: summarise, and suggest next steps.

These two endpoints previously returned canned text. `ai-summarize` read the
`ai_summary` column — written only by the email-intake path, so a ticket raised
through the portal always got "AI summary not yet generated" — and `ai-suggest`
returned three hard-coded sentences with the priority interpolated. Both logged
an `AI_DECISION` audit row, which made the trail claim a decision that no model
had made.

That is worse than the feature being absent. A button labelled *AI Summarize*
that returns a fixed string teaches people the AI is useless, and an audit row
saying a decision was taken when none was is a false record.

Both now call the model through `llm_client`, grounded in the ticket the caller
can already open. Three things follow from that grounding:

* **The context comes from a ticket the permission check already passed.** The
  route resolves the ticket through `_get_ticket_or_404`, which applies the
  same visibility filter as the list endpoint, so there is no second access
  path to keep in step.
* **Nothing is invented about the ticket.** The prompt supplies the fields and
  forbids adding to them, in the same style as the chat assistant's prompt,
  because a 9B local model follows explicit prohibitions far more reliably
  than tone guidance.
* **Failure is visible, not papered over.** If the model is unreachable the
  caller gets the reason, `success=false` on the interaction log, and no audit
  row claiming a decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger
from app.models.ticket import Ticket
from app.services import llm_client

log = get_logger(__name__)

#: Comments included as context. Enough for the model to see the shape of the
#: conversation without spending the whole budget re-reading a long thread.
MAX_COMMENTS = 6
MAX_COMMENT_CHARS = 400


@dataclass
class TicketAIResult:
    ok: bool
    text: str = ""
    bullets: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


def _fmt(value) -> str:
    if value is None:
        return "not set"
    return getattr(value, "value", value)


def build_ticket_context(ticket: Ticket, comments: list | None = None) -> str:
    """The facts the model is allowed to use, and nothing else."""
    lines = [
        "# TICKET",
        f"Number: {ticket.ticket_number}",
        f"Title: {ticket.title}",
        f"Status: {_fmt(ticket.status)}",
        f"Priority: {_fmt(ticket.priority)}",
        f"Source: {_fmt(ticket.source)}",
    ]
    if ticket.department:
        lines.append(f"Department: {ticket.department}")
    if ticket.ai_category:
        lines.append(f"Category (from intake): {ticket.ai_category}")
    if ticket.sla_breached:
        lines.append("SLA: BREACHED")

    lines.append("")
    lines.append("Description:")
    lines.append((ticket.description or "(none)")[:2000])

    if comments:
        lines.append("")
        lines.append(f"# CONVERSATION (most recent {min(len(comments), MAX_COMMENTS)})")
        for c in comments[-MAX_COMMENTS:]:
            author = getattr(getattr(c, "author", None), "full_name", None) or "staff"
            kind = "internal note" if getattr(c, "is_internal", False) else "reply"
            body = (getattr(c, "body", "") or "")[:MAX_COMMENT_CHARS]
            lines.append(f"- {author} ({kind}): {body}")

    return "\n".join(lines)


SUMMARY_PROMPT = "\n".join([
    "You summarise support tickets for SUCCESS Bank staff.",
    "",
    "RULES",
    "- Use only the TICKET block. Never invent numbers, names, amounts, dates "
    "or statuses.",
    "- If the ticket does not say something, do not say it either.",
    "- Never output full account numbers or customer PII; keep any masking "
    "already present.",
    "",
    "STYLE",
    "- At most 70 words, in two or three plain sentences.",
    "- Lead with what the problem is, then where it has got to.",
    "- No preamble, no headings, no bullet list, no closing offer to help.",
])

SUGGEST_PROMPT = "\n".join([
    "You suggest next steps on support tickets for SUCCESS Bank staff.",
    "",
    "RULES",
    "- Use only the TICKET block. Never invent facts about the ticket.",
    "- Suggest actions a person takes, not things the system does "
    "automatically.",
    "- For fraud, AML, regulatory or compliance matters, recommend the "
    "compliance team rather than giving a regulatory opinion.",
    "- Never suggest anything that would expose customer PII.",
    "",
    "FORMAT",
    "- Exactly 3 to 5 lines.",
    "- Each line is one action, starting with a verb, at most 18 words.",
    "- No numbering, no bullet characters, no heading, no closing line.",
])


def _to_bullets(text: str, limit: int = 5) -> list[str]:
    """Split the model's reply into clean action lines.

    Small local models add bullet characters and numbering however firmly the
    prompt forbids it, so the markers are stripped here rather than trusted
    away. Anything that survives as an empty string is dropped.
    """
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^\s*(?:[-*•‣◦]|\d+[.)])\s*", "", line)
        line = line.strip(" \t.-")
        if line:
            out.append(line[:200])
        if len(out) >= limit:
            break
    return out


async def summarise_ticket(ticket: Ticket, comments: list | None = None) -> TicketAIResult:
    result = await llm_client.generate(
        build_ticket_context(ticket, comments),
        [],
        system_prompt=SUMMARY_PROMPT,
        max_tokens=settings.AI_CHAT_MAX_TOKENS,
    )
    if not result.ok:
        return TicketAIResult(ok=False, error=result.text)
    return TicketAIResult(
        ok=True,
        text=(result.text or "").strip(),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


async def suggest_next_steps(ticket: Ticket, comments: list | None = None) -> TicketAIResult:
    result = await llm_client.generate(
        build_ticket_context(ticket, comments),
        [],
        system_prompt=SUGGEST_PROMPT,
        max_tokens=settings.AI_CHAT_MAX_TOKENS,
    )
    if not result.ok:
        return TicketAIResult(ok=False, error=result.text)

    bullets = _to_bullets(result.text)
    if not bullets:
        # A reply with no usable line is a failure, not an empty success.
        # Returning [] would render as a working feature that suggests nothing.
        return TicketAIResult(
            ok=False,
            error="The model returned no usable suggestions. Try again.",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
    return TicketAIResult(
        ok=True,
        bullets=bullets,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )

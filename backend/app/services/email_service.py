"""Email intake service — polls IMAP and converts inbound emails to tickets.

Flow:
1. poll_imap_mailbox() fetches UNSEEN messages from the configured mailbox.
2. Each raw email is passed to process_inbound_email().
3. If the email is a reply (In-Reply-To header or TKT-* subject), a comment
   is added to the existing ticket.
4. If it is a new message, AIService.extract_email_entities() generates a
   title/category and TicketService.create_ticket() creates the ticket.
5. InboundEmail is stored with status PROCESSED or FAILED.
6. The IMAP message is marked \\Seen after processing.

imaplib is used intentionally (sync, run in executor) so this code is safe
to call from a periodic background job (APScheduler).
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import re
import uuid
from datetime import UTC, datetime
from email.header import decode_header as _decode_header
from email.message import Message
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.email_intake import EmailStatus, InboundEmail
from app.models.ticket import Ticket, TicketSource
from app.models.user import User
from app.schemas.ticket import CommentCreate, TicketCreate
from app.services.ai_service import AIService
from app.services.ticket_service import TicketService

log = get_logger(__name__)

# Pattern to detect ticket number in subject or body
_TKT_PATTERN = re.compile(r"TKT-\d{8}-\d{5}", re.IGNORECASE)

# Spam keywords (rudimentary)
_SPAM_KEYWORDS = [
    "click here", "free money", "winner", "lottery", "unclaimed", "nigerian",
    "earn cash", "urgent transfer", "bank account number required",
]


def _decode_mime_header(value: str | None) -> str:
    """Decode a possibly RFC-2047-encoded header value to plain string."""
    if not value:
        return ""
    parts = []
    for segment, charset in _decode_header(value):
        if isinstance(segment, bytes):
            parts.append(segment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(segment)
    return "".join(parts)


def _extract_body(msg: Message) -> tuple[str, str]:
    """Return (text_body, html_body) from an email.message.Message."""
    text_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            if "attachment" in cd:
                continue
            if ct == "text/plain" and not text_body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_body = payload.decode(charset, errors="replace")
            elif ct == "text/html" and not html_body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html_body = payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_body = text
            else:
                text_body = text

    return text_body, html_body


def _count_attachments(msg: Message) -> int:
    count = 0
    for part in msg.walk():
        if part.get("Content-Disposition", "").startswith("attachment"):
            count += 1
    return count


def _parse_raw_email(raw_bytes: bytes) -> dict[str, Any]:
    """Parse raw RFC-2822 bytes into a normalised dict."""
    msg: Message = email.message_from_bytes(raw_bytes)

    message_id = msg.get("Message-ID", "").strip()
    from_header = _decode_mime_header(msg.get("From", ""))
    to_header = _decode_mime_header(msg.get("To", ""))
    subject = _decode_mime_header(msg.get("Subject", ""))
    in_reply_to = msg.get("In-Reply-To", "").strip() or None
    references = msg.get("References", "").strip() or None
    date_str = msg.get("Date", "")
    x_ticket_id = msg.get("X-Ticket-ID", "").strip() or None

    # Best-effort date parsing
    try:
        import email.utils as _eu
        parsed_date = _eu.parsedate_to_datetime(date_str)
        received_at: datetime = parsed_date.astimezone(UTC)
    except Exception:
        received_at = datetime.now(UTC)

    # SPF / DKIM (added by MTA as headers)
    spf_result = msg.get("Received-SPF", "").lower()
    spf_pass: bool | None = None
    if "pass" in spf_result:
        spf_pass = True
    elif "fail" in spf_result or "softfail" in spf_result:
        spf_pass = False

    dkim_result = msg.get("DKIM-Signature", "")
    dkim_pass: bool | None = True if dkim_result else None  # presence = signed

    # Sender domain
    sender_domain: str | None = None
    if "@" in from_header:
        sender_domain = from_header.split("@")[-1].split(">")[0].strip()

    text_body, html_body = _extract_body(msg)
    attachments_count = _count_attachments(msg)

    # CC
    cc_raw = msg.get("CC", "") or msg.get("Cc", "")
    cc_addresses = [addr.strip() for addr in cc_raw.split(",") if addr.strip()] or None

    # Thread ID (first reference or message_id itself)
    thread_id: str | None = None
    if references:
        thread_id = references.split()[0]
    elif in_reply_to:
        thread_id = in_reply_to
    elif message_id:
        thread_id = message_id

    return {
        "message_id": message_id,
        "from_address": from_header,
        "to_address": to_header,
        "cc_addresses": cc_addresses,
        "subject": subject,
        "body_text": text_body or None,
        "body_html": html_body or None,
        "in_reply_to": in_reply_to,
        "references": references,
        "thread_id": thread_id,
        "received_at": received_at,
        "attachments_count": attachments_count,
        "x_ticket_id": x_ticket_id,
        "spf_pass": spf_pass,
        "dkim_pass": dkim_pass,
        "sender_domain": sender_domain,
        "is_reply": bool(in_reply_to),
    }


class EmailService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_inbound_email(self, raw_email_data: dict) -> InboundEmail:
        """
        Process a single parsed email dict produced by _parse_raw_email().

        Returns the persisted InboundEmail record.
        """
        message_id: str = raw_email_data.get("message_id", "")

        # Deduplication check
        existing_stmt = select(InboundEmail).where(InboundEmail.message_id == message_id)
        existing = (await self.db.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            log.info("email.duplicate_detected", message_id=message_id)
            existing.status = EmailStatus.DUPLICATE.value  # type: ignore[assignment]
            await self.db.flush()
            return existing

        spam_score = self._calculate_spam_score(raw_email_data)
        is_spam = spam_score >= 0.7

        record = InboundEmail(
            message_id=message_id or f"no-id-{uuid.uuid4()}",
            from_address=raw_email_data.get("from_address", ""),
            to_address=raw_email_data.get("to_address", ""),
            cc_addresses=raw_email_data.get("cc_addresses"),
            subject=raw_email_data.get("subject") or None,
            body_text=raw_email_data.get("body_text"),
            body_html=raw_email_data.get("body_html"),
            received_at=raw_email_data.get("received_at", datetime.now(UTC)),
            status=EmailStatus.PENDING.value,  # type: ignore[assignment]
            is_spam=is_spam,
            spam_score=spam_score,
            is_phishing=False,
            is_reply=raw_email_data.get("is_reply", False),
            in_reply_to=raw_email_data.get("in_reply_to"),
            thread_id=raw_email_data.get("thread_id"),
            attachments_count=raw_email_data.get("attachments_count", 0),
            spf_pass=raw_email_data.get("spf_pass"),
            dkim_pass=raw_email_data.get("dkim_pass"),
            sender_domain=raw_email_data.get("sender_domain"),
        )
        self.db.add(record)
        await self.db.flush()

        if is_spam:
            record.status = EmailStatus.SPAM.value  # type: ignore[assignment]
            await self.db.flush()
            log.info("email.spam_filtered", message_id=message_id, spam_score=spam_score)
            await self.db.commit()
            return record

        try:
            await self._route_email(record, raw_email_data)
            record.status = EmailStatus.PROCESSED.value  # type: ignore[assignment]
            record.processed_at = datetime.now(UTC)
        except Exception as exc:
            record.status = EmailStatus.FAILED.value  # type: ignore[assignment]
            record.processing_error = str(exc)[:500]
            log.exception("email.processing_failed", message_id=message_id, error=str(exc))

        await self.db.flush()
        await self.db.commit()
        return record

    # ------------------------------------------------------------------
    # Routing logic
    # ------------------------------------------------------------------

    async def _route_email(self, record: InboundEmail, raw_data: dict) -> None:
        """Decide whether to add a comment or create a new ticket."""
        existing_ticket = await self._find_existing_ticket(
            in_reply_to=raw_data.get("in_reply_to"),
            subject=raw_data.get("subject", ""),
            x_ticket_id=raw_data.get("x_ticket_id"),
        )

        if existing_ticket is not None:
            await self._add_email_comment(existing_ticket, record, raw_data)
            record.ticket_id = existing_ticket.id
        else:
            ticket = await self._create_ticket_from_email(record, raw_data)
            record.ticket_id = ticket.id

    async def _add_email_comment(
        self,
        ticket: Ticket,
        record: InboundEmail,
        raw_data: dict,
    ) -> None:
        """Append the email body as a public comment on the existing ticket."""
        from app.models.comment import CommentSource

        body = raw_data.get("body_text") or raw_data.get("body_html") or "(no body)"
        comment_data = CommentCreate(body=body[:5000], is_internal=False)

        svc = TicketService(self.db)
        await svc.add_comment(
            ticket_id=ticket.id,
            data=comment_data,
            author_id=None,
            source=CommentSource.EMAIL,
        )
        log.info(
            "email.comment_added",
            ticket_id=str(ticket.id),
            message_id=record.message_id,
        )

    async def _create_ticket_from_email(
        self,
        record: InboundEmail,
        raw_data: dict,
    ) -> Ticket:
        """Use AIService to extract entities then create a new ticket."""
        ai = AIService(self.db)
        subject = raw_data.get("subject") or "Support Request"
        body = raw_data.get("body_text") or raw_data.get("body_html") or ""
        from_address = raw_data.get("from_address", "")

        extraction = await ai.extract_email_entities(
            subject=subject,
            body=body,
            from_address=from_address,
        )

        # Find or create a system/bot reporter user for email intake
        system_user = await self._get_or_create_system_user()

        ticket_data = TicketCreate(
            title=extraction.title[:255],
            description=extraction.summary or body[:2000],
            priority=extraction.priority,  # type: ignore[arg-type]
            source=TicketSource.EMAIL,
        )

        svc = TicketService(self.db)
        ticket = await svc.create_ticket(
            data=ticket_data,
            reporter_id=system_user.id,
            source=TicketSource.EMAIL,
        )

        # Stamp email tracking fields directly (bypass service to avoid extra commit)
        ticket.email_message_id = record.message_id
        ticket.email_from = from_address[:255] if from_address else None
        ticket.email_subject = subject[:500] if subject else None
        ticket.ai_category = extraction.category
        ticket.ai_confidence = extraction.confidence
        ticket.ai_risk_score = extraction.risk_score

        await self.db.flush()
        log.info(
            "email.ticket_created",
            ticket_id=str(ticket.id),
            ticket_number=ticket.ticket_number,
            message_id=record.message_id,
        )
        return ticket

    async def _get_or_create_system_user(self) -> User:
        """Return the system/bot user used as reporter for email-created tickets."""
        system_email = "system@successbank.internal"
        stmt = select(User).where(User.email == system_email)
        user = (await self.db.execute(stmt)).scalar_one_or_none()
        if user:
            return user

        # Fallback: return any active user (e.g. first admin)
        stmt = select(User).where(User.is_active.is_(True)).limit(1)
        user = (await self.db.execute(stmt)).scalar_one_or_none()
        if user:
            return user

        raise RuntimeError("No active users found to act as email intake reporter.")

    # ------------------------------------------------------------------
    # IMAP polling
    # ------------------------------------------------------------------

    def _poll_imap_sync(self) -> list[bytes]:
        """Synchronous IMAP fetch — runs in executor."""
        host = getattr(settings, "IMAP_HOST", "localhost")
        user = getattr(settings, "IMAP_USER", "")
        password = getattr(settings, "IMAP_PASSWORD", "")

        raw_emails: list[bytes] = []

        try:
            mail = imaplib.IMAP4_SSL(host)
            mail.login(user, password)
            mail.select("INBOX")

            _status, message_ids = mail.search(None, "UNSEEN")
            if _status != "OK":
                return []

            id_list = message_ids[0].split()
            for msg_id in id_list:
                _typ, msg_data = mail.fetch(msg_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        raw_emails.append(response_part[1])
                # Mark as seen
                mail.store(msg_id, "+FLAGS", "\\Seen")

            mail.logout()
        except imaplib.IMAP4.error as exc:
            log.error("email.imap_error", error=str(exc))
        except OSError as exc:
            log.error("email.imap_connection_error", error=str(exc))

        return raw_emails

    async def poll_imap_mailbox(self) -> int:
        """Poll IMAP mailbox for UNSEEN emails and process each one. Returns count processed."""
        loop = asyncio.get_event_loop()
        raw_emails: list[bytes] = await loop.run_in_executor(None, self._poll_imap_sync)

        processed = 0
        for raw_bytes in raw_emails:
            try:
                parsed = _parse_raw_email(raw_bytes)
                await self.process_inbound_email(parsed)
                processed += 1
            except Exception as exc:
                log.exception("email.poll.process_error", error=str(exc))

        log.info("email.poll_complete", processed=processed, total_fetched=len(raw_emails))
        return processed

    # ------------------------------------------------------------------
    # Spam scoring
    # ------------------------------------------------------------------

    def _calculate_spam_score(self, email_data: dict) -> float:
        """
        Heuristic spam score in [0.0, 1.0].

        Signals:
        - Missing Message-ID            +0.15
        - No subject                    +0.10
        - Spam keyword hits (per word)  +0.10 each (max 0.5)
        - SPF fail                      +0.20
        - DKIM absent                   +0.10
        - Very short body               +0.05
        """
        score = 0.0

        if not email_data.get("message_id"):
            score += 0.15
        if not email_data.get("subject"):
            score += 0.10

        body = (email_data.get("body_text") or "").lower()
        subject = (email_data.get("subject") or "").lower()
        combined = subject + " " + body

        keyword_hits = sum(1 for kw in _SPAM_KEYWORDS if kw in combined)
        score += min(keyword_hits * 0.10, 0.50)

        if email_data.get("spf_pass") is False:
            score += 0.20
        if not email_data.get("dkim_pass"):
            score += 0.10

        body_len = len(body.strip())
        if body_len < 20:
            score += 0.05

        return min(score, 1.0)

    # ------------------------------------------------------------------
    # Ticket-lookup helpers
    # ------------------------------------------------------------------

    async def _find_existing_ticket(
        self,
        in_reply_to: str | None,
        subject: str,
        x_ticket_id: str | None = None,
    ) -> Ticket | None:
        """
        Try to find an existing ticket this email is replying to.

        Checks (in order):
        1. X-Ticket-ID custom header
        2. In-Reply-To matches email_message_id on a ticket
        3. TKT-YYYYMMDD-NNNNN pattern in the subject line
        """
        # 1. Custom header
        if x_ticket_id:
            stmt = select(Ticket).where(Ticket.ticket_number == x_ticket_id.upper())
            ticket = (await self.db.execute(stmt)).scalar_one_or_none()
            if ticket:
                return ticket

        # 2. In-Reply-To → email_message_id
        if in_reply_to:
            stmt = select(Ticket).where(Ticket.email_message_id == in_reply_to)
            ticket = (await self.db.execute(stmt)).scalar_one_or_none()
            if ticket:
                return ticket

        # 3. TKT number in subject
        if subject:
            match = _TKT_PATTERN.search(subject)
            if match:
                tkt_number = match.group(0).upper()
                stmt = select(Ticket).where(Ticket.ticket_number == tkt_number)
                ticket = (await self.db.execute(stmt)).scalar_one_or_none()
                if ticket:
                    return ticket

        return None

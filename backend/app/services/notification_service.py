"""Notification service — email notifications for ticket lifecycle events.

Uses aiosmtplib for fully async SMTP delivery. Falls back gracefully if SMTP
is unavailable (logs the failure, does not raise into the caller).
"""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.ticket import Ticket

log = get_logger(__name__)


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Core send
    # ------------------------------------------------------------------

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        """Send a plain-text email via SMTP. Returns True on success."""
        if not to or not subject:
            log.warning("notification.send_email.missing_fields", to=to, subject=subject)
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            smtp_kwargs: dict = {
                "hostname": settings.SMTP_HOST,
                "port": settings.SMTP_PORT,
                "timeout": 10,
            }

            # Use STARTTLS for port 587, plain for local/dev (1025)
            if settings.SMTP_PORT in (587, 465):
                smtp_kwargs["use_tls"] = settings.SMTP_PORT == 465
                smtp_kwargs["start_tls"] = settings.SMTP_PORT == 587

            async with aiosmtplib.SMTP(**smtp_kwargs) as smtp:
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    await smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                await smtp.send_message(msg)

            log.info("notification.email_sent", to=to, subject=subject)
            return True

        except Exception as exc:
            log.error("notification.send_email.failed", to=to, subject=subject, error=str(exc))
            return False

    # ------------------------------------------------------------------
    # Ticket lifecycle notifications
    # ------------------------------------------------------------------

    async def notify_ticket_created(self, ticket: Ticket, reporter_email: str) -> None:
        """Notify the reporter that their ticket has been created."""
        subject = f"[SUCCESS Bank Support] Ticket {ticket.ticket_number} Created"
        body = (
            f"Dear Customer,\n\n"
            f"Your support request has been received and assigned ticket number "
            f"{ticket.ticket_number}.\n\n"
            f"Subject: {ticket.title}\n"
            f"Priority: {ticket.priority if isinstance(ticket.priority, str) else ticket.priority.value}\n\n"
            f"Our team will respond to you shortly. You can refer to your ticket number "
            f"in all future communications.\n\n"
            f"Thank you for contacting SUCCESS Bank Support.\n\n"
            f"Regards,\nSUCCESS Bank Support Team"
        )
        await self.send_email(reporter_email, subject, body)

    async def notify_ticket_assigned(self, ticket: Ticket, assignee_email: str) -> None:
        """Notify an agent that a ticket has been assigned to them."""
        subject = f"[SUCCESS Bank] Ticket {ticket.ticket_number} Assigned to You"
        priority = ticket.priority if isinstance(ticket.priority, str) else ticket.priority.value
        body = (
            f"Hello,\n\n"
            f"Ticket {ticket.ticket_number} has been assigned to you.\n\n"
            f"Title: {ticket.title}\n"
            f"Priority: {priority.upper()}\n"
            f"Status: {ticket.status if isinstance(ticket.status, str) else ticket.status.value}\n\n"
            f"Please review and take appropriate action.\n\n"
            f"Regards,\nSUCCESS Bank Ticketing System"
        )
        await self.send_email(assignee_email, subject, body)

    async def notify_sla_breach(
        self,
        ticket: Ticket,
        manager_emails: list[str],
    ) -> None:
        """Notify managers when a ticket has breached its SLA deadline."""
        if not manager_emails:
            return

        subject = f"[SLA BREACH] Ticket {ticket.ticket_number} — Immediate Attention Required"
        priority = ticket.priority if isinstance(ticket.priority, str) else ticket.priority.value
        resolution_due = (
            ticket.resolution_due_at.isoformat() if ticket.resolution_due_at else "N/A"
        )
        body = (
            f"ALERT: SLA Breach Detected\n\n"
            f"Ticket: {ticket.ticket_number}\n"
            f"Title: {ticket.title}\n"
            f"Priority: {priority.upper()}\n"
            f"Status: {ticket.status if isinstance(ticket.status, str) else ticket.status.value}\n"
            f"Resolution Due: {resolution_due}\n"
            f"Assignee ID: {ticket.assignee_id or 'Unassigned'}\n\n"
            f"This ticket has exceeded its SLA deadline and requires immediate attention.\n\n"
            f"Regards,\nSUCCESS Bank SLA Monitor"
        )

        for email in manager_emails:
            await self.send_email(email, subject, body)

    async def notify_escalation(
        self,
        ticket: Ticket,
        escalatee_email: str,
        reason: str,
    ) -> None:
        """Notify the escalation target about a newly escalated ticket."""
        subject = f"[ESCALATION] Ticket {ticket.ticket_number} Escalated to You"
        priority = ticket.priority if isinstance(ticket.priority, str) else ticket.priority.value
        body = (
            f"Hello,\n\n"
            f"Ticket {ticket.ticket_number} has been escalated to you.\n\n"
            f"Title: {ticket.title}\n"
            f"Priority: {priority.upper()}\n"
            f"Escalation Reason: {reason}\n\n"
            f"Please review this ticket urgently and take the necessary action.\n\n"
            f"Regards,\nSUCCESS Bank Ticketing System"
        )
        await self.send_email(escalatee_email, subject, body)

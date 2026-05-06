"""SMTP email adapter.

Designed so a real SES/SendGrid implementation slots in by overriding
`send_email`. In dev we point SMTP_HOST at a local MailHog (port 1025)
and the messages stay in-memory.

Failures are swallowed and logged — the persisted Notification row is
the source of truth for delivery state, and the worker can retry later.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class EmailAdapter:
    def send(self, *, to: str, subject: str, body: str) -> bool:
        if not to or not settings.SMTP_HOST:
            log.info("email_skipped", to=to, subject=subject)
            return False
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = settings.SMTP_FROM
            msg["To"] = to
            msg.set_content(body)

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
                if settings.SMTP_USER:
                    s.starttls()
                    s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
            log.info("email_sent", to=to, subject=subject)
            return True
        except Exception:  # noqa: BLE001
            log.exception("email_send_failed", to=to, subject=subject)
            return False

"""SMS adapter — logging stub. Swap to Twilio / vendor implementation
without touching NotificationService.
"""

from __future__ import annotations

from app.core.logging import get_logger

log = get_logger(__name__)


class SMSAdapter:
    def send(self, *, to: str, body: str) -> bool:
        if not to:
            return False
        log.info("sms_dispatched", to=to, body=body[:160])
        return True

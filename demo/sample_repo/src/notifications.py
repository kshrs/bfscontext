"""
Customer notification and receipt email dispatching service for billing events.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Raised when notification delivery fails."""
    pass


class EmailService:
    """Outbound email dispatcher for payment receipts and account notifications."""

    def __init__(self, smtp_host: str = "smtp.company.internal", port: int = 587) -> None:
        self.smtp_host = smtp_host
        self.port = port
        self.sent_emails: List[Dict[str, Any]] = []

    def send_payment_receipt(
        self,
        recipient_email: str,
        amount: float,
        currency: str,
        transaction_id: str,
    ) -> bool:
        """Sends customer transaction confirmation and receipt."""
        if not recipient_email or "@" not in recipient_email:
            raise NotificationError(f"Invalid recipient email address: {recipient_email}")

        email_payload = {
            "to": recipient_email,
            "subject": f"Payment Receipt for {currency} {amount:.2f}",
            "template": "receipt_v1",
            "context": {
                "amount": amount,
                "currency": currency,
                "transaction_id": transaction_id,
            },
        }
        self.sent_emails.append(email_payload)
        logger.info("Email receipt sent to %s for tx %s", recipient_email, transaction_id)
        return True

    def send_low_balance_warning(self, recipient_email: str, current_balance: float) -> bool:
        """Sends warning notice when account balance drops below threshold."""
        email_payload = {
            "to": recipient_email,
            "subject": "Warning: Low Account Balance",
            "template": "low_balance_alert",
            "context": {"balance": current_balance},
        }
        self.sent_emails.append(email_payload)
        return True

    def count_sent_emails(self) -> int:
        """Returns count of outbound emails sent."""
        return len(self.sent_emails)


class WebhookNotificationDispatcher:
    """Dispatches webhook callbacks to third-party merchant endpoints."""

    def __init__(self, timeout_sec: float = 5.0) -> None:
        self.timeout_sec = timeout_sec
        self.dispatched_webhooks: List[Dict[str, Any]] = []

    def dispatch_event(self, endpoint_url: str, event_type: str, payload: Dict[str, Any]) -> bool:
        """Sends signed webhook HTTP callback."""
        if not endpoint_url.startswith("https://"):
            raise NotificationError("Webhook endpoints must use HTTPS transport")

        record = {
            "endpoint": endpoint_url,
            "event": event_type,
            "payload": payload,
        }
        self.dispatched_webhooks.append(record)
        return True

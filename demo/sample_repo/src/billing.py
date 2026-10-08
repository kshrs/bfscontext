"""
Billing module: Process user charges and handle Stripe webhooks.
"""

from typing import Any, Dict, Optional

from auth import verify_webhook_signature
from config import Config
from database import DatabaseClient


class PaymentError(Exception):
    """Raised when payment processing fails."""
    pass


def validate_charge_amount(amount: float) -> bool:
    """Helper validator ensuring positive charge amount."""
    return amount > 0.0


def charge_user(
    user_id: str,
    amount: float,
    currency: str = Config.CURRENCY,
    db: Optional[DatabaseClient] = None,
) -> Dict[str, Any]:
    """
    Charges a user specified amount and updates balance in database.
    """
    if not validate_charge_amount(amount):
        raise ValueError(f"Invalid charge amount: {amount}")

    client = db or DatabaseClient()
    user = client.get_user_record(user_id)
    if not user:
        raise PaymentError(f"User {user_id} not found")

    new_balance = user["balance"] - amount
    client.update_balance(user_id, new_balance)

    return {
        "status": "success",
        "user_id": user_id,
        "amount": amount,
        "currency": currency,
        "new_balance": new_balance,
    }


def handle_stripe_webhook(payload: str, signature: str) -> Dict[str, Any]:
    """
    Handles incoming Stripe webhook payload after verifying signature.
    """
    if not verify_webhook_signature(payload, signature):
        raise PaymentError("Invalid webhook signature")
    return {"status": "processed", "payload": payload}

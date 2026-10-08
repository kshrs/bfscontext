"""
Billing module: Process user charges, handle Stripe webhooks, and manage subscription invoicing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from auth import verify_webhook_signature, PermissionChecker
from config import Config
from database import DatabaseClient, AuditLogRepository

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    """Raised when payment processing fails."""
    pass


class InsufficientFundsError(PaymentError):
    """Raised when user balance is insufficient for charge."""
    pass


class InvalidWebhookPayloadError(PaymentError):
    """Raised when Stripe webhook payload or signature is invalid."""
    pass


def validate_charge_amount(amount: float) -> bool:
    """Helper validator ensuring positive charge amount."""
    return amount > 0.0


def format_currency_amount(amount: float, currency: str = "USD") -> str:
    """Formats numeric amount into ISO currency string."""
    return f"{currency.upper()} {amount:.2f}"


def charge_user(
    user_id: str,
    amount: float,
    currency: str = Config.CURRENCY,
    db: Optional[DatabaseClient] = None,
) -> Dict[str, Any]:
    """
    Charges a user specified amount and updates balance in database.
    Target function for demo delegation and context compilation.
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


def refund_user(
    user_id: str,
    amount: float,
    reason: str = "customer_request",
    db: Optional[DatabaseClient] = None,
) -> Dict[str, Any]:
    """
    Processes transaction refund back to customer balance.
    """
    if not validate_charge_amount(amount):
        raise ValueError(f"Refund amount must be positive: {amount}")

    client = db or DatabaseClient()
    user = client.get_user_record(user_id)
    if not user:
        raise PaymentError(f"User {user_id} not found for refund")

    new_balance = user["balance"] + amount
    client.update_balance(user_id, new_balance)
    client.record_transaction(user_id, amount, "refund", status="completed")

    return {
        "status": "refunded",
        "user_id": user_id,
        "refund_amount": amount,
        "new_balance": new_balance,
        "reason": reason,
    }


class SubscriptionManager:
    """Manages recurring billing cycles and subscription tiers."""

    PLAN_PRICING: Dict[str, float] = {
        "starter": 29.00,
        "professional": 99.00,
        "enterprise": 499.00,
    }

    def __init__(self, db: Optional[DatabaseClient] = None) -> None:
        self.db = db or DatabaseClient()

    def calculate_proration(self, current_plan: str, new_plan: str, days_remaining: int) -> float:
        """Calculates prorated billing adjustment across plan changes."""
        curr_price = self.PLAN_PRICING.get(current_plan, 0.0)
        new_price = self.PLAN_PRICING.get(new_plan, 0.0)
        daily_diff = (new_price - curr_price) / 30.0
        return round(max(0.0, daily_diff * days_remaining), 2)

    def execute_subscription_charge(self, user_id: str, plan_name: str) -> Dict[str, Any]:
        """Bills user for monthly plan fee."""
        if plan_name not in self.PLAN_PRICING:
            raise PaymentError(f"Unknown subscription plan: {plan_name}")
        amount = self.PLAN_PRICING[plan_name]
        return charge_user(user_id, amount, db=self.db)

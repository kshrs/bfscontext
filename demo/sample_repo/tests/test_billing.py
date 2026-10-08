"""
Unit and integration tests for demo/sample_repo billing and payment pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to sys.path so test can import directly
SRC_PATH = Path(__file__).resolve().parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest
from billing import (
    PaymentError,
    charge_user,
    format_currency_amount,
    handle_stripe_webhook,
    refund_user,
    validate_charge_amount,
    SubscriptionManager,
)
from database import DatabaseClient
from auth import verify_webhook_signature, PermissionChecker
from config import Config


def test_validate_charge_amount():
    assert validate_charge_amount(50.0) is True
    assert validate_charge_amount(-10.0) is False
    assert validate_charge_amount(0.0) is False


def test_format_currency_amount():
    assert format_currency_amount(100.5, "USD") == "USD 100.50"
    assert format_currency_amount(0.0, "EUR") == "EUR 0.00"


def test_charge_user_success():
    db = DatabaseClient()
    result = charge_user("user_123", 25.0, db=db)
    assert result["status"] == "success"
    assert result["user_id"] == "user_123"
    assert result["amount"] == 25.0
    assert result["new_balance"] == 75.0


def test_charge_user_missing_user():
    db = DatabaseClient()
    with pytest.raises(PaymentError, match="not found"):
        charge_user("nonexistent_user", 25.0, db=db)


def test_charge_user_invalid_amount():
    db = DatabaseClient()
    with pytest.raises(ValueError, match="Invalid charge amount"):
        charge_user("user_123", -5.0, db=db)


def test_refund_user_success():
    db = DatabaseClient()
    res = refund_user("user_123", 30.0, reason="test_refund", db=db)
    assert res["status"] == "refunded"
    assert res["new_balance"] == 130.0


def test_webhook_signature_verification():
    assert verify_webhook_signature("payload_data", "whsec_valid123456") is True
    assert verify_webhook_signature("payload_data", "invalid_prefix") is False
    assert verify_webhook_signature("", "whsec_valid123") is False


def test_handle_stripe_webhook():
    res = handle_stripe_webhook('{"event": "payment_succeeded"}', "whsec_secret1234")
    assert res["status"] == "processed"

    with pytest.raises(PaymentError):
        handle_stripe_webhook('{"event": "bad"}', "invalid_sig")


def test_permission_checker():
    assert PermissionChecker.can_perform_action("admin", "billing:charge") is True
    assert PermissionChecker.can_perform_action("auditor", "billing:charge") is False

    with pytest.raises(PermissionError):
        PermissionChecker.require_permission("auditor", "billing:charge")


def test_subscription_manager_proration():
    mgr = SubscriptionManager()
    proration = mgr.calculate_proration("starter", "professional", days_remaining=15)
    # (99 - 29) / 30 * 15 = 35.0
    assert proration == 35.0


def test_subscription_manager_charge():
    db = DatabaseClient()
    mgr = SubscriptionManager(db=db)
    res = mgr.execute_subscription_charge("user_123", "starter")
    assert res["status"] == "success"
    assert res["amount"] == 29.0

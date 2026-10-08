"""Billing and charge engine."""
from typing import Dict, Any, Optional
from gateway import StripeGateway, GatewayResponse
from user_model import User

class BillingException(Exception):
    pass

def calculate_prorated_tax(amount: float, tax_rate: float) -> float:
    """Calculates tax on transaction."""
    return round(amount * tax_rate, 2)

def execute_user_charge(
    user: User,
    amount_cents: int,
    gateway: Optional[StripeGateway] = None
) -> Dict[str, Any]:
    """
    Executes payment charge for a specific user account.
    Target function for benchmarking task.
    """
    if amount_cents <= 0:
        raise BillingException("Amount must be positive")
    if not user.is_active:
        raise BillingException("User is deactivated")

    gw = gateway or StripeGateway()
    res: GatewayResponse = gw.process_charge(user.user_id, amount_cents)
    if not res.success:
        raise BillingException(f"Charge failed: {res.error_code}")

    return {
        "status": "completed",
        "user_id": user.user_id,
        "amount_cents": amount_cents,
        "transaction_id": res.transaction_id
    }

def refund_transaction(transaction_id: str) -> bool:
    """Unrelated billing function."""
    return True

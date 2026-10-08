"""External payment gateway abstractions."""
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class GatewayResponse:
    success: bool
    transaction_id: str
    error_code: str = ""

class StripeGateway:
    def process_charge(self, customer_id: str, amount_cents: int) -> GatewayResponse:
        return GatewayResponse(success=True, transaction_id=f"tx_{customer_id}_123")

"""
Audit log, metric counter, and billing reconciliation models for sample repo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class InvoiceItem:
    """Line item on customer invoice."""
    description: str
    quantity: int
    unit_price: float

    @property
    def total(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass
class Invoice:
    """Customer invoice aggregate."""
    invoice_id: str
    user_id: str
    items: List[InvoiceItem] = field(default_factory=list)
    issued_at: float = field(default_factory=time.time)
    paid: bool = False

    def add_item(self, description: str, quantity: int, unit_price: float) -> None:
        self.items.append(InvoiceItem(description, quantity, unit_price))

    @property
    def subtotal(self) -> float:
        return round(sum(item.total for item in self.items), 2)

    @property
    def total(self) -> float:
        # Standard 8% tax calculation
        tax = round(self.subtotal * 0.08, 2)
        return round(self.subtotal + tax, 2)

    def mark_paid(self) -> None:
        self.paid = True


class BillingReconciliationEngine:
    """Audits payment gateway deposits against internal database ledger."""

    def __init__(self) -> None:
        self.reconciled_batches: List[str] = []

    def reconcile_ledger_vs_gateway(
        self,
        internal_ledger_sum: float,
        gateway_deposit_sum: float,
        discrepancy_tolerance: float = 0.01,
    ) -> Dict[str, Any]:
        """Calculates discrepancy between gateway and ledger."""
        diff = round(abs(internal_ledger_sum - gateway_deposit_sum), 2)
        matched = diff <= discrepancy_tolerance
        batch_id = f"batch_{int(time.time())}"
        if matched:
            self.reconciled_batches.append(batch_id)
        return {
            "batch_id": batch_id,
            "matched": matched,
            "difference": diff,
            "ledger_total": internal_ledger_sum,
            "gateway_total": gateway_deposit_sum,
        }

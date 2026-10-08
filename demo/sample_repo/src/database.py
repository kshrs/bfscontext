"""
Database client simulating relational database operations, transactions, and audit logs.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Raised when connection to the database cannot be established."""
    pass


class RecordNotFoundError(Exception):
    """Raised when query returns zero records."""
    pass


class DatabaseClient:
    """Simulates relational database connection, session management, and CRUD."""

    def __init__(self, connection_url: str = "sqlite:///:memory:"):
        self.connection_url = connection_url
        self._connected = True
        self._users: Dict[str, Dict[str, Any]] = {
            "user_123": {"id": "user_123", "balance": 100.0, "status": "active", "email": "alice@test.com"},
            "user_456": {"id": "user_456", "balance": 500.0, "status": "active", "email": "bob@test.com"},
            "user_inactive": {"id": "user_inactive", "balance": 10.0, "status": "suspended", "email": "charlie@test.com"},
        }
        self._transactions: List[Dict[str, Any]] = []

    def get_user_record(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves user profile and balance record by ID."""
        if not self._connected:
            raise DatabaseConnectionError("Database connection is closed")
        return self._users.get(user_id)

    def update_balance(self, user_id: str, new_balance: float) -> bool:
        """Updates user balance atomically."""
        if not self._connected:
            raise DatabaseConnectionError("Database connection is closed")
        if user_id not in self._users:
            raise RecordNotFoundError(f"User {user_id} not found in database")
        self._users[user_id]["balance"] = round(new_balance, 2)
        return True

    def record_transaction(
        self,
        user_id: str,
        amount: float,
        transaction_type: str,
        status: str = "completed",
    ) -> str:
        """Inserts an immutable ledger transaction entry."""
        tx_id = f"tx_{user_id}_{int(time.time() * 1000)}"
        tx_record = {
            "tx_id": tx_id,
            "user_id": user_id,
            "amount": amount,
            "type": transaction_type,
            "status": status,
            "timestamp": time.time(),
        }
        self._transactions.append(tx_record)
        return tx_id

    def list_transactions_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Queries transaction history for a specific user account."""
        return [tx for tx in self._transactions if tx["user_id"] == user_id]

    def close(self) -> None:
        """Closes the underlying database connection pool."""
        self._connected = False


class AuditLogRepository:
    """Manages compliance and security audit logs."""

    def __init__(self, db_client: Optional[DatabaseClient] = None) -> None:
        self.db_client = db_client or DatabaseClient()
        self._audit_records: List[Dict[str, Any]] = []

    def write_audit_event(
        self,
        event_name: str,
        actor_id: str,
        target_resource: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Records an immutable security audit event."""
        event = {
            "event_name": event_name,
            "actor_id": actor_id,
            "target_resource": target_resource,
            "metadata": metadata or {},
            "logged_at": time.time(),
        }
        self._audit_records.append(event)
        logger.info("AUDIT EVENT: %s by %s on %s", event_name, actor_id, target_resource)

    def count_events(self) -> int:
        """Returns total audit events recorded."""
        return len(self._audit_records)

"""
Database client simulating DB operations.
"""

from typing import Any, Dict, Optional


class DatabaseClient:
    def __init__(self, connection_url: str = "sqlite:///:memory:"):
        self.connection_url = connection_url

    def get_user_record(self, user_id: str) -> Optional[Dict[str, Any]]:
        return {"id": user_id, "balance": 100.0, "status": "active"}

    def update_balance(self, user_id: str, new_balance: float) -> bool:
        return True

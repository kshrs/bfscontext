"""
Generator script to build a large, multi-module benchmark repository for realistic evaluation.
"""

from pathlib import Path


def generate_benchmark_repo(base_dir: Path) -> Path:
    repo_dir = base_dir / "large_benchmark_repo"
    src_dir = repo_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # 1. core/config.py
    (src_dir / "config.py").write_text('''"""Core system configuration."""
import os

class AppConfig:
    ENV: str = os.getenv("APP_ENV", "production")
    DEBUG: bool = False
    PORT: int = 8080
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key")
    DB_POOL_SIZE: int = 20
''', encoding="utf-8")

    # 2. core/security.py
    (src_dir / "security.py").write_text('''"""Cryptographic and hashing utilities."""
import hashlib
import hmac

def hash_token(token: str) -> str:
    """Hashes API token using SHA256."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def verify_signature(payload: str, signature: str, secret: str) -> bool:
    """Verifies HMAC signature."""
    mac = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)
''', encoding="utf-8")

    # 3. auth/user_model.py
    (src_dir / "user_model.py").write_text('''"""User and permission models."""
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class User:
    user_id: str
    email: str
    roles: List[str]
    is_active: bool = True

def is_admin_user(user: User) -> bool:
    """Checks admin role."""
    return "admin" in user.roles
''', encoding="utf-8")

    # 4. auth/auth_service.py
    (src_dir / "auth_service.py").write_text('''"""Authentication management service."""
from security import hash_token
from user_model import User

class AuthService:
    def __init__(self):
        self.session_store = {}

    def authenticate_user(self, token: str) -> bool:
        hashed = hash_token(token)
        return hashed in self.session_store

    def register_session(self, user: User, token: str) -> None:
        self.session_store[hash_token(token)] = user
''', encoding="utf-8")

    # 5. payment/gateway.py
    (src_dir / "gateway.py").write_text('''"""External payment gateway abstractions."""
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
''', encoding="utf-8")

    # 6. payment/billing_engine.py
    (src_dir / "billing_engine.py").write_text('''"""Billing and charge engine."""
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
''', encoding="utf-8")

    # 7. notifications/email_service.py
    (src_dir / "email_service.py").write_text('''"""Outbound email dispatch system."""
class EmailDispatcher:
    def send_welcome_email(self, email: str) -> bool:
        return True

    def send_receipt(self, email: str, tx_id: str, amount: float) -> bool:
        return True
''', encoding="utf-8")

    # 8. analytics/metrics_collector.py
    (src_dir / "metrics_collector.py").write_text('''"""Usage analytics and aggregation pipeline."""
from typing import Dict

class MetricsCollector:
    def __init__(self):
        self.counters = {}

    def increment(self, metric: str, count: int = 1) -> None:
        self.counters[metric] = self.counters.get(metric, 0) + count

    def report_all(self) -> Dict[str, int]:
        return dict(self.counters)
''', encoding="utf-8")

    # 9. storage/s3_client.py
    (src_dir / "s3_client.py").write_text('''"""Cloud blob storage wrapper."""
class S3Client:
    def upload_file(self, bucket: str, key: str, data: bytes) -> bool:
        return True

    def download_file(self, bucket: str, key: str) -> bytes:
        return b""
''', encoding="utf-8")

    # 10. reports/invoice_generator.py
    (src_dir / "invoice_generator.py").write_text('''"""PDF invoice generator and formatter."""
class InvoiceGenerator:
    def generate_pdf_invoice(self, order_id: str, items: list) -> bytes:
        return b"%PDF-1.4 dummy invoice"
''', encoding="utf-8")

    return repo_dir


if __name__ == "__main__":
    p = generate_benchmark_repo(Path(__file__).parent)
    print(f"Benchmark repository generated at {p}")

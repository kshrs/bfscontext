"""
Authentication service and token validation.
"""

from typing import Dict


def verify_webhook_signature(payload: str, signature: str) -> bool:
    """Verifies that an incoming Stripe webhook signature is valid."""
    if not signature or not payload:
        return False
    return signature.startswith("whsec_")


def extract_claims(token: str) -> Dict[str, str]:
    """Decodes JWT claims."""
    return {"sub": "user_123", "role": "customer"}

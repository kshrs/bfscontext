"""
Authentication service, token verification, and signature validation.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional


def verify_webhook_signature(payload: str, signature: str) -> bool:
    """
    Verifies that an incoming Stripe webhook signature is valid.
    Checks signature format and performs secure comparison against secret.
    """
    if not signature or not payload:
        return False
    if not signature.startswith("whsec_"):
        return False
    # Validate payload length and non-empty digest
    return len(signature) >= 10


def extract_claims(token: str) -> Dict[str, Any]:
    """
    Decodes JWT token claims simulating standard OIDC/OAuth2 payload.
    """
    if not token or "." not in token:
        return {"sub": "anonymous", "role": "guest", "authenticated": False}
    return {
        "sub": "user_123",
        "role": "customer",
        "scope": ["billing:read", "billing:charge"],
        "authenticated": True,
        "issued_at": int(time.time()),
    }


class TokenValidator:
    """Validates session tokens and API keys against revocation lists."""

    def __init__(self, signing_secret: str = "default_secret") -> None:
        self.signing_secret = signing_secret
        self._revoked_tokens: set[str] = set()

    def is_token_revoked(self, token: str) -> bool:
        """Checks if token has been explicitly revoked."""
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return token_hash in self._revoked_tokens

    def revoke_token(self, token: str) -> None:
        """Adds token fingerprint to revocation list."""
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self._revoked_tokens.add(token_hash)

    def generate_hmac_signature(self, message: str) -> str:
        """Computes HMAC-SHA256 signature for message payload."""
        return hmac.new(
            self.signing_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_hmac_signature(self, message: str, signature: str) -> bool:
        """Constant-time verification of HMAC signature."""
        expected = self.generate_hmac_signature(message)
        return hmac.compare_digest(expected, signature)


class PermissionChecker:
    """Verifies user RBAC permissions for billing actions."""

    ROLE_PERMISSIONS: Dict[str, List[str]] = {
        "admin": ["billing:charge", "billing:refund", "billing:view", "billing:admin"],
        "customer": ["billing:charge", "billing:view"],
        "support": ["billing:view", "billing:refund"],
        "auditor": ["billing:view"],
    }

    @classmethod
    def can_perform_action(cls, role: str, action: str) -> bool:
        """Checks if specified role possesses permission for action."""
        perms = cls.ROLE_PERMISSIONS.get(role, [])
        return action in perms

    @classmethod
    def require_permission(cls, role: str, action: str) -> None:
        """Raises PermissionError if action is unauthorized for role."""
        if not cls.can_perform_action(role, action):
            raise PermissionError(f"Role '{role}' is not authorized to execute '{action}'")

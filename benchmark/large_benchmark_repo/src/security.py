"""Cryptographic and hashing utilities."""
import hashlib
import hmac

def hash_token(token: str) -> str:
    """Hashes API token using SHA256."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def verify_signature(payload: str, signature: str, secret: str) -> bool:
    """Verifies HMAC signature."""
    mac = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)

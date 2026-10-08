"""
Unit tests and verification harness for capsule_engine.py
Author: kshrs
"""

import os
import tempfile
from capsule_engine import (
    ASTCodeSlicer,
    estimate_tokens,
    generate_context_capsule,
    get_git_head_sha,
    infer_target_symbol,
    slice_code_target,
)

SAMPLE_CODE = '''import os
import sys
import json
from datetime import datetime
from typing import Dict, Optional

GLOBAL_CONFIG = {"api_version": "v3", "timeout": 30}

class PaymentProcessor:
    """Enterprise payment handler with Stripe v3 webhooks."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.retries = 3

    def validate_signature(self, payload: bytes, sig_header: str) -> bool:
        return len(sig_header) > 10 and b"test" not in payload

    def charge_user(self, user_id: str, amount_cents: int, currency: str = "USD") -> Dict:
        """Charges a registered customer with idempotency."""
        if amount_cents <= 0:
            raise ValueError("Amount must be positive")
        tx_id = f"tx_{user_id}_{amount_cents}"
        return {"status": "success", "tx_id": tx_id, "amount": amount_cents, "currency": currency}

    def refund_user(self, tx_id: str, reason: str = "customer_request") -> Dict:
        return {"status": "refunded", "tx_id": tx_id, "reason": reason}

def helper_format_currency(cents: int) -> str:
    return f"${cents / 100:.2f}"
'''


def test_token_estimator():
    tokens = estimate_tokens("def charge_user(id, amt): return True")
    assert tokens > 0, "Token count should be greater than 0"
    print(f"✓ estimate_tokens test passed (Estimated: {tokens})")


def test_symbol_inference():
    symbol = infer_target_symbol(SAMPLE_CODE, "Write unit tests for charge_user function")
    assert symbol == "charge_user", f"Expected charge_user, got {symbol}"
    print(f"✓ infer_target_symbol test passed (Resolved: {symbol})")


def test_ast_slicing():
    sliced, imports, resolved = slice_code_target(SAMPLE_CODE, "charge_user")
    assert "def charge_user" in sliced
    assert "refund_user" not in sliced, "Unrelated function should be excluded"
    assert any("import json" in imp for imp in imports), "Imports should be extracted"
    print("✓ slice_code_target test passed")


def test_full_capsule_generation():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tmp:
        tmp.write(SAMPLE_CODE)
        tmp_path = tmp.name

    try:
        capsule = generate_context_capsule(
            file_path=tmp_path,
            subtask_description="Generate isolated unit test for charge_user method",
            intent_summary="Migrating billing system to Stripe v3 idempotency standard",
            target_symbol="charge_user",
        )

        assert capsule.target_symbol == "charge_user"
        assert "[TASK INSTRUCTIONS]" in capsule.capsule_prompt
        assert "[IMMUTABLE CODE CONTRACTS]" in capsule.capsule_prompt
        assert "refund_user" not in capsule.capsule_prompt
        assert capsule.tokens_saved > 0
        assert capsule.compression_ratio > 0.0

        print(f"✓ generate_context_capsule test passed:")
        print(f"  - Target Symbol: {capsule.target_symbol}")
        print(f"  - Raw Tokens: {capsule.raw_file_tokens} -> Capsule Tokens: {capsule.capsule_tokens}")
        print(f"  - Tokens Saved: {capsule.tokens_saved} ({capsule.compression_ratio*100:.1f}% reduction)")
        print(f"  - Pinned SHA: {capsule.commit_sha[:8]}")
    finally:
        os.remove(tmp_path)


def test_hash_pinning_deprecation():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tmp:
        tmp.write(SAMPLE_CODE)
        tmp_path = tmp.name

    try:
        # Pass a bogus or outdated commit sha
        capsule = generate_context_capsule(
            file_path=tmp_path,
            subtask_description="Test charge_user",
            intent_summary="Legacy session intent",
            pinned_commit_sha="1111111111111111111111111111111111111111",
        )

        assert not capsule.is_sha_active
        assert "[HISTORICAL INTENT: SHA 11111111 - MAY BE DEPRECATED" in capsule.capsule_prompt
        print("✓ Hash-Pinning deprecation warning test passed")
    finally:
        os.remove(tmp_path)


if __name__ == "__main__":
    print("\n--- Running Capsule Engine Core Verification Suite ---")
    test_token_estimator()
    test_symbol_inference()
    test_ast_slicing()
    test_full_capsule_generation()
    test_hash_pinning_deprecation()
    print("--- ALL TESTS PASSED SUCCESSFULLY! ---\n")

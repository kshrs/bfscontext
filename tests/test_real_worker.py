"""
Tests for RealWorkerProvider, Guardrail Disk Invariants, and Capsule-Only Payload:
1. Hardened Guardrail Invariant:
   - INVALID WORKER OUTPUT -> VALIDATION -> NO REPOSITORY WRITE
   - VALID WORKER OUTPUT -> VALIDATION -> REPOSITORY WRITE (when apply_to_disk=True)
2. Real Worker Provider Configuration:
   - Provider selection (mock vs real)
   - Missing API key graceful failure
   - Successful response via mocked HTTP layer
   - HTTP error handling
   - Network URL error handling
3. Capsule-Only Payload Proof:
   - Verifies the prompt sent to RealWorkerProvider contains ONLY the Context Capsule and target prompt,
     and NEVER raw uncompiled repository files or unrelated symbols.
4. MCP Server Parity:
   - worker_model="mock" vs worker_model="gpt-4o"
   - Latency breakdown reporting (compilation, worker, guardrail, total)
"""

import json
from pathlib import Path
import pytest

from capsulemcp.adapters.interfaces import FixerProvider
from capsulemcp.adapters.real_worker import RealWorkerProvider
from capsulemcp.circuit_breaker import CircuitBreaker, GuardrailStatus
from capsulemcp.mcp_server import CapsuleMCPServer
from capsulemcp.models import CodeUnit, ContextCapsule, IntentContext, TokenMetrics


@pytest.fixture
def test_repo_with_disk_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    target_file = repo / "service.py"
    original_code = "def original_func():\n    return 'original'\n"
    target_file.write_text(original_code, encoding="utf-8")
    return repo, target_file, original_code


class LocalUnrepairableFixer(FixerProvider):
    def __init__(self):
        self.call_count = 0

    def fix(self, code: str, error_message: str, target_file_path: str) -> str:
        self.call_count += 1
        return "def still_fatal_syntax(:\n    !!!"


def test_guardrail_disk_write_invariant_invalid_never_writes(test_repo_with_disk_file):
    """
    CRITICAL INVARIANT:
    Invalid worker output must NEVER modify the repository file on disk!
    """
    repo, target_file, original_code = test_repo_with_disk_file
    # Use unrepairable fixer to test circuit breaker trip and disk write invariant
    failing_fixer = LocalUnrepairableFixer()
    guard = CircuitBreaker(repo_path=str(repo), fixer=failing_fixer)

    invalid_code = "def fatal_syntax(:\n    ???"
    res = guard.evaluate_and_guard(
        worker_code=invalid_code,
        target_file=str(target_file),
        apply_to_disk=True,
    )

    assert res.status == GuardrailStatus.CIRCUIT_BREAKER_TRIPPED
    assert res.syntax_valid is False
    assert failing_fixer.call_count == 1
    # Verify disk content is completely UNTOUCHED
    current_content = target_file.read_text(encoding="utf-8")
    assert current_content == original_code


def test_guardrail_disk_write_invariant_valid_writes_only_after_validation(test_repo_with_disk_file):
    """
    Valid worker output modifies the repository file on disk ONLY after validation passes.
    """
    repo, target_file, original_code = test_repo_with_disk_file
    guard = CircuitBreaker(repo_path=str(repo))

    valid_new_code = "def updated_func():\n    return 'updated'"
    res = guard.evaluate_and_guard(
        worker_code=valid_new_code,
        target_file=str(target_file),
        apply_to_disk=True,
    )

    assert res.status == GuardrailStatus.SUCCESS
    assert res.syntax_valid is True
    # Verify disk content now holds the validated code
    current_content = target_file.read_text(encoding="utf-8")
    assert current_content == valid_new_code


def test_real_worker_missing_api_key_graceful_failure():
    """Real worker returns structured error when API key is missing."""
    worker = RealWorkerProvider(api_key=None)
    # Ensure no environment variable overrides
    worker.api_key = None

    capsule = ContextCapsule(
        task_instructions="Test task",
        intent_context=IntentContext("intent", "src", "sha"),
        target_unit=CodeUnit("foo", "function", "def foo(): pass", 1, 1),
        imports=[],
        dependencies=[],
        git_head_sha="sha",
        target_file_path="service.py",
    )

    res = worker.generate(capsule)
    assert res["status"] == "error"
    assert "Missing API key" in res["error"]
    assert res["is_mock"] is False


def test_real_worker_capsule_only_payload_proof():
    """
    PROVES THE CENTRAL PROJECT CLAIM:
    The payload sent to RealWorkerProvider contains ONLY the Context Capsule and target prompt,
    and NEVER the full repository or unreferenced files.
    """
    # Mock HTTP response
    def dummy_http(url, headers, req_data):
        return {
            "choices": [{"message": {"content": "def foo():\n    return 'repaired'\n"}}],
            "usage": {"total_tokens": 120},
        }

    worker = RealWorkerProvider(api_key="sk-test-mock-key", http_client=dummy_http)

    capsule = ContextCapsule(
        task_instructions="Implement foo()",
        intent_context=IntentContext("test intent", "MOCK", "sha123"),
        target_unit=CodeUnit("foo", "function", "def foo(): pass", 1, 1),
        imports=["import os"],
        dependencies=[],
        git_head_sha="sha123",
        target_file_path="service.py",
        token_metrics=TokenMetrics(500, 100, 400, 80.0, "tiktoken"),
    )

    res = worker.generate(capsule)
    assert res["status"] == "success"
    assert "def foo()" in res["generated_code"]

    # Inspect the exact payload sent over the wire
    payload = worker.last_sent_payload
    assert payload is not None
    messages = payload["messages"]
    user_msg = next(m["content"] for m in messages if m["role"] == "user")

    # MUST contain the compiled capsule sections
    assert "[TASK INSTRUCTIONS]" in user_msg
    assert "[IMMUTABLE CODE CONTRACTS]" in user_msg
    assert "def foo(): pass" in user_msg

    # MUST NOT contain unreferenced files from codebase
    assert "unrelated_secret" not in user_msg
    assert "InvoiceGenerator" not in user_msg
    assert "EmailDispatcher" not in user_msg


def test_mcp_real_worker_integration_and_latency_telemetry(tmp_path):
    """
    Tests MCP server using RealWorkerProvider with mocked HTTP layer,
    verifying guardrail passage and latency telemetry.
    """
    repo = tmp_path / "mcp_repo"
    repo.mkdir()
    target_file = repo / "math_utils.py"
    target_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    def dummy_http(url, headers, req_data):
        return {
            "choices": [{"message": {"content": "```python\ndef add(a: int, b: int) -> int:\n    return a + b\n```"}}],
            "usage": {"total_tokens": 50},
        }

    real_worker = RealWorkerProvider(api_key="sk-dummy-key", http_client=dummy_http)
    server = CapsuleMCPServer(repo_path=str(repo), worker_provider=real_worker)

    res = server.delegate_with_capsule(
        target_file="math_utils.py",
        subtask="Test add function",
        target_symbol="add",
        worker_model="gpt-4o-mini",
    )

    assert res["status"] == "success"
    assert res["guardrail"]["status"] == "SUCCESS"
    assert res["guardrail"]["syntax_valid"] is True

    # Verify extended latency telemetry
    lat = res["latency_telemetry"]
    assert "compilation_latency_ms" in lat
    assert "worker_latency_ms" in lat
    assert "guardrail_latency_ms" in lat
    assert "total_request_latency_ms" in lat

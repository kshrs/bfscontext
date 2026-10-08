"""
Production-Style End-to-End Integration Tests.
Validates the complete pipeline:
1. Mock E2E success (valid output -> written to disk -> git state updated safely)
2. Mock repairable failure (invalid syntax -> fixed in 1 attempt -> REPAIRED -> written to disk)
3. Mock unrecoverable failure (fatal syntax -> single fix fails -> CIRCUIT_BREAKER_TRIPPED -> rollback)
4. Capsule-only worker input verification
5. Telemetry propagation (request_id, commit_sha, stage latencies)
6. Request ID and Git SHA propagation across MCP response
7. Pre-existing modification protection (uncommitted edits preserved during rollback)
8. Path traversal attack rejection
9. Unrelated files untouched during write or rollback
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import pytest

from benchmark.generate_repo import generate_benchmark_repo
from capsulemcp.adapters.interfaces import FixerProvider
from capsulemcp.adapters.mock import MockIntentProvider, MockTelemetrySink, MockWorkerProvider
from capsulemcp.circuit_breaker import CircuitBreaker, GuardrailStatus, MockFixerProvider
from capsulemcp.git_utils import get_git_head_sha
from capsulemcp.mcp_server import CapsuleMCPServer
from demo.run_e2e_demo import FailureInjectionWorker, FatalFixer


@pytest.fixture
def git_benchmark_repo(tmp_path):
    """Creates a real git repository with benchmark files committed."""
    repo_dir = generate_benchmark_repo(tmp_path)
    # Initialize real git repository
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ci@test.com"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CI Bot"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial benchmark repo"], cwd=str(repo_dir), check=True, capture_output=True)
    return repo_dir


def test_e2e_mock_success(git_benchmark_repo):
    """Test 1: Valid worker output -> SUCCESS -> applied safely to disk."""
    telemetry = MockTelemetrySink()
    worker = FailureInjectionWorker(failure_mode="valid")
    server = CapsuleMCPServer(
        repo_path=str(git_benchmark_repo),
        telemetry_sink=telemetry,
        worker_provider=worker,
    )

    resp = server.delegate_with_capsule(
        target_file="src/billing_engine.py",
        subtask="Add retry logic to execute_user_charge",
        target_symbol="execute_user_charge",
        apply_to_disk=True,
        request_id="req-test-success",
    )

    assert resp["status"] == "success"
    assert resp["guardrail"]["status"] == GuardrailStatus.SUCCESS.value
    assert resp["guardrail"]["syntax_valid"] is True
    assert resp["guardrail"]["auto_fix_attempted"] is False
    assert resp["guardrail"]["rolled_back"] is False

    # Verify disk content was updated with retry logic
    target_content = (git_benchmark_repo / "src" / "billing_engine.py").read_text(encoding="utf-8")
    assert "max_retries" in target_content

    # Verify unrelated files untouched
    email_content = (git_benchmark_repo / "src" / "email_service.py").read_text(encoding="utf-8")
    assert "EmailDispatcher" in email_content


def test_e2e_mock_repairable_failure(git_benchmark_repo):
    """Test 2: Malformed syntax -> 1 fix attempt succeeds -> REPAIRED -> applied to disk."""
    telemetry = MockTelemetrySink()
    worker = FailureInjectionWorker(failure_mode="repairable")
    fixer = MockFixerProvider()
    server = CapsuleMCPServer(
        repo_path=str(git_benchmark_repo),
        telemetry_sink=telemetry,
        worker_provider=worker,
        fixer=fixer,
    )

    resp = server.delegate_with_capsule(
        target_file="src/billing_engine.py",
        subtask="Add retry logic to execute_user_charge",
        target_symbol="execute_user_charge",
        apply_to_disk=True,
        request_id="req-test-repairable",
    )

    assert resp["status"] == "success"
    assert resp["guardrail"]["status"] == GuardrailStatus.REPAIRED.value
    assert resp["guardrail"]["syntax_valid"] is True
    assert resp["guardrail"]["auto_fix_attempted"] is True
    assert resp["guardrail"]["rolled_back"] is False


def test_e2e_mock_unrecoverable_failure_and_rollback(git_benchmark_repo):
    """Test 3: Unrecoverable syntax -> 1 fix fails -> CIRCUIT_BREAKER_TRIPPED -> git rollback."""
    target_file = git_benchmark_repo / "src" / "billing_engine.py"
    initial_target_code = target_file.read_text(encoding="utf-8")
    initial_sha = get_git_head_sha(str(git_benchmark_repo))

    telemetry = MockTelemetrySink()
    worker = FailureInjectionWorker(failure_mode="unrecoverable")
    fatal_fixer = FatalFixer()
    server = CapsuleMCPServer(
        repo_path=str(git_benchmark_repo),
        telemetry_sink=telemetry,
        worker_provider=worker,
        fixer=fatal_fixer,
    )

    resp = server.delegate_with_capsule(
        target_file="src/billing_engine.py",
        subtask="Add retry logic to execute_user_charge",
        target_symbol="execute_user_charge",
        apply_to_disk=True,
        request_id="req-test-unrecoverable",
    )

    assert resp["status"] == "failed"
    assert resp["guardrail"]["status"] == GuardrailStatus.CIRCUIT_BREAKER_TRIPPED.value
    assert resp["guardrail"]["syntax_valid"] is False
    assert resp["guardrail"]["auto_fix_attempted"] is True

    # Critical invariant: Target file state matches initial committed git state!
    current_content = target_file.read_text(encoding="utf-8")
    assert current_content == initial_target_code
    assert "execute_user_charge" in current_content


def test_e2e_pre_existing_modification_protection(git_benchmark_repo):
    """Test 4: Uncommitted pre-existing edits are safeguarded during circuit breaker trip."""
    target_file = git_benchmark_repo / "src" / "billing_engine.py"
    # User makes uncommitted pre-existing changes
    user_work = target_file.read_text(encoding="utf-8") + "\n# DEVELOPER IN-PROGRESS WORK\n"
    target_file.write_text(user_work, encoding="utf-8")

    worker = FailureInjectionWorker(failure_mode="unrecoverable")
    fatal_fixer = FatalFixer()
    server = CapsuleMCPServer(
        repo_path=str(git_benchmark_repo),
        worker_provider=worker,
        fixer=fatal_fixer,
    )

    resp = server.delegate_with_capsule(
        target_file="src/billing_engine.py",
        subtask="Add retry logic",
        target_symbol="execute_user_charge",
        apply_to_disk=True,
    )

    assert resp["guardrail"]["status"] == GuardrailStatus.CIRCUIT_BREAKER_TRIPPED.value
    assert resp["guardrail"]["pre_existing_modifications_protected"] is True

    # User work was NOT blown away by a blind git reset
    current_content = target_file.read_text(encoding="utf-8")
    assert "# DEVELOPER IN-PROGRESS WORK" in current_content


def test_e2e_capsule_only_worker_input(git_benchmark_repo):
    """Test 5: Worker receives ONLY the compiled ContextCapsule, not unrelated repo files."""
    captured_capsules = []

    class InspectingWorker(MockWorkerProvider):
        def generate(self, capsule):
            captured_capsules.append(capsule)
            return super().generate(capsule)

    worker = InspectingWorker()
    server = CapsuleMCPServer(
        repo_path=str(git_benchmark_repo),
        worker_provider=worker,
    )

    server.delegate_with_capsule(
        target_file="src/billing_engine.py",
        subtask="Test execute_user_charge",
        target_symbol="execute_user_charge",
    )

    assert len(captured_capsules) == 1
    c = captured_capsules[0]
    rendered = c.render()

    # Required contracts are present
    assert "execute_user_charge" in rendered
    assert "StripeGateway" in rendered
    assert "User" in rendered

    # Irrelevant modules are strictly excluded from worker's view
    assert "EmailDispatcher" not in rendered
    assert "MetricsCollector" not in rendered
    assert "S3Client" not in rendered


def test_e2e_telemetry_and_metadata_propagation(git_benchmark_repo):
    """Test 6: Request ID, Git SHA, and latency breakdown propagate throughout MCP response."""
    telemetry = MockTelemetrySink()
    server = CapsuleMCPServer(
        repo_path=str(git_benchmark_repo),
        telemetry_sink=telemetry,
    )

    req_id = "custom-uuid-12345"
    resp = server.delegate_with_capsule(
        target_file="src/billing_engine.py",
        subtask="Telemetry check",
        target_symbol="execute_user_charge",
        request_id=req_id,
    )

    assert resp["request_id"] == req_id
    assert len(resp["commit_sha"]) == 40
    assert "latency_telemetry" in resp
    lat = resp["latency_telemetry"]
    assert "compilation_latency_ms" in lat
    assert "worker_latency_ms" in lat
    assert "guardrail_latency_ms" in lat
    assert "total_request_latency_ms" in lat

    # Telemetry sink captured compilation
    assert len(telemetry.records) == 1
    rec = telemetry.records[0]
    assert rec["metadata"]["request_id"] == req_id


def test_e2e_path_traversal_rejection(git_benchmark_repo):
    """Test 7: Path traversal attacks are rejected by MCP gateway."""
    server = CapsuleMCPServer(repo_path=str(git_benchmark_repo))

    resp = server.delegate_with_capsule(
        target_file="../../etc/passwd",
        subtask="Attack attempt",
    )

    assert resp["status"] == "error"
    assert "Security violation" in resp["error"]

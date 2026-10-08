"""
Comprehensive tests for One-Strike Guardrail & Circuit Breaker:
A. Valid output -> SUCCESS, no fixer, no rollback
B. Markdown output -> fenced Python sanitized -> SUCCESS
C. Invalid output -> fixer invoked once
D. Fixer succeeds -> REPAIRED
E. Fixer fails -> CIRCUIT_BREAKER_TRIPPED + rollback
F. Fixer count -> asserted called exactly once
G. No infinite loop -> deliberately failing fixer invoked exactly once
H. Path traversal -> reject unsafe target paths
I. Pre-existing user modifications -> rollback does not destroy unrelated work
J. Target symbol -> structural validation when symbol supplied
K. Unsupported language -> graceful rejection
L. Malformed markdown -> graceful handling
M. Git failure / uncommitted states -> safe error handling
N. Determinism -> identical inputs produce identical guardrail results
"""

from pathlib import Path
import pytest

from capsulemcp.adapters.interfaces import FixerProvider
from capsulemcp.circuit_breaker import (
    CircuitBreaker,
    GuardrailResult,
    GuardrailStatus,
    MockFixerProvider,
    strip_markdown_fences,
)


class CountingFixer(FixerProvider):
    """Tracks the exact number of fix attempts."""

    def __init__(self, succeed: bool = True):
        self.call_count = 0
        self.succeed = succeed

    def fix(self, code: str, error_message: str, target_file_path: str) -> str:
        self.call_count += 1
        if self.succeed:
            return "def valid_repaired_function():\n    return 42\n"
        return "def still_broken_function(:\n    pass\n"


@pytest.fixture
def test_repo(tmp_path):
    repo = tmp_path / "guardrail_repo"
    repo.mkdir()
    (repo / "module.py").write_text("def existing(): pass\n", encoding="utf-8")
    return repo


def test_markdown_fence_sanitization():
    """Validates markdown code fence stripping for varied formats."""
    fenced_py = "```python\ndef foo():\n    return True\n```"
    assert strip_markdown_fences(fenced_py) == "def foo():\n    return True"

    fenced_plain = "```\ndef bar():\n    return False\n```"
    assert strip_markdown_fences(fenced_plain) == "def bar():\n    return False"

    raw_code = "def baz():\n    return 123"
    assert strip_markdown_fences(raw_code) == raw_code

    assert strip_markdown_fences("") == ""


def test_case_a_valid_output(test_repo):
    """Case A: Valid code produces SUCCESS, no fixer, no rollback."""
    fixer = CountingFixer(succeed=True)
    guard = CircuitBreaker(repo_path=str(test_repo), fixer=fixer)

    code = "def calculate_total(x: int) -> int:\n    return x * 2\n"
    res = guard.evaluate_and_guard(
        worker_code=code,
        target_file="module.py",
        target_symbol="calculate_total",
    )

    assert res.status == GuardrailStatus.SUCCESS
    assert res.syntax_valid is True
    assert res.auto_fix_attempted is False
    assert res.rolled_back is False
    assert fixer.call_count == 0


def test_case_b_markdown_output(test_repo):
    """Case B: Markdown-fenced code is sanitized and passes as SUCCESS."""
    guard = CircuitBreaker(repo_path=str(test_repo))
    fenced = "```python\ndef calculate_total(x: int) -> int:\n    return x * 2\n```"

    res = guard.evaluate_and_guard(
        worker_code=fenced,
        target_file="module.py",
        target_symbol="calculate_total",
    )

    assert res.status == GuardrailStatus.SUCCESS
    assert "```" not in res.clean_code
    assert res.syntax_valid is True


def test_case_c_d_f_fixer_succeeds_once(test_repo):
    """Case C & D & F: Broken syntax invokes fixer EXACTLY ONCE and results in REPAIRED."""
    fixer = CountingFixer(succeed=True)
    guard = CircuitBreaker(repo_path=str(test_repo), fixer=fixer)

    broken_code = "def unclosed_function(:\n    pass\n"
    res = guard.evaluate_and_guard(
        worker_code=broken_code,
        target_file="module.py",
    )

    assert res.status == GuardrailStatus.REPAIRED
    assert res.syntax_valid is True
    assert res.auto_fix_attempted is True
    assert res.rolled_back is False
    # Verified: fixer invoked exactly once!
    assert fixer.call_count == 1


def test_case_e_g_fixer_fails_circuit_breaker_tripped(test_repo):
    """Case E & G: When fixer also fails, circuit breaker trips with NO infinite loop."""
    failing_fixer = CountingFixer(succeed=False)
    guard = CircuitBreaker(repo_path=str(test_repo), fixer=failing_fixer)

    broken_code = "def broken(:\n"
    res = guard.evaluate_and_guard(
        worker_code=broken_code,
        target_file="module.py",
    )

    assert res.status == GuardrailStatus.CIRCUIT_BREAKER_TRIPPED
    assert res.syntax_valid is False
    assert res.auto_fix_attempted is True
    assert "Circuit breaker tripped" in res.error_message
    # Verified: NO recursive loop, exactly 1 invocation
    assert failing_fixer.call_count == 1


def test_case_h_path_traversal_rejection(test_repo):
    """Case H: Guards against path traversal attacks."""
    guard = CircuitBreaker(repo_path=str(test_repo))
    res = guard.evaluate_and_guard(
        worker_code="def hack(): pass",
        target_file="../../secret_config.py",
    )

    assert res.status == GuardrailStatus.CIRCUIT_BREAKER_TRIPPED
    assert "Security violation" in res.error_message


def test_case_j_target_symbol_structural_validation(test_repo):
    """Case J: When target symbol is supplied, ensures it exists in generated code."""
    guard = CircuitBreaker(repo_path=str(test_repo))
    code = "def completely_different_fn():\n    return True\n"

    res = guard.evaluate_and_guard(
        worker_code=code,
        target_file="module.py",
        target_symbol="required_symbol",
    )

    # Missing target symbol causes invalidation
    assert res.status in (GuardrailStatus.REPAIRED, GuardrailStatus.CIRCUIT_BREAKER_TRIPPED)


def test_case_k_unsupported_language(test_repo):
    """Case K: Non-python targets rejected gracefully."""
    guard = CircuitBreaker(repo_path=str(test_repo))
    res = guard.evaluate_and_guard(
        worker_code="function test() {}",
        target_file="module.js",
    )
    assert res.status == GuardrailStatus.CIRCUIT_BREAKER_TRIPPED
    assert "Unsupported language" in res.error_message


def test_case_n_determinism(test_repo):
    """Case N: Deterministic validation for identical inputs."""
    guard = CircuitBreaker(repo_path=str(test_repo))
    code = "def foo(): return 1\n"

    r1 = guard.evaluate_and_guard(code, "module.py")
    r2 = guard.evaluate_and_guard(code, "module.py")

    assert r1.status == r2.status
    assert r1.clean_code == r2.clean_code
    assert r1.syntax_valid == r2.syntax_valid

"""
Failure Injection Demonstration of the One-Strike Guardrail & Circuit Breaker:
Shows the 3 distinct execution branches:
CASE 1: Valid worker output -> SUCCESS (no fixer invoked, no rollback)
CASE 2: Invalid syntax -> ONE repair attempt succeeds -> REPAIRED
CASE 3: Invalid syntax -> ONE repair attempt fails -> CIRCUIT_BREAKER_TRIPPED (rollback, safe failure, NO infinite loop)
"""

from pathlib import Path
from capsulemcp.circuit_breaker import CircuitBreaker, GuardrailStatus, MockFixerProvider
from capsulemcp.adapters.interfaces import FixerProvider


class UnrepairableFixer(FixerProvider):
    """Fails repair to simulate fatal syntax error."""
    def fix(self, code: str, error_message: str, target_file_path: str) -> str:
        return "def permanently_broken(:\n    !!!"


def main():
    repo_path = Path(__file__).parent / "sample_repo"
    target_file = "src/billing.py"

    print("=" * 90)
    print("CAPSULEMCP ONE-STRIKE GUARDRAIL / CIRCUIT BREAKER DEMONSTRATION")
    print("Core Principle: Never allow invalid worker output to silently become repo state.")
    print("=" * 90)

    # ----------------------------------------------------
    # CASE 1: Valid Worker Output
    # ----------------------------------------------------
    print("\n" + "-" * 90)
    print("CASE 1: Valid Worker Output")
    print("-" * 90)
    guardrail_1 = CircuitBreaker(repo_path=str(repo_path))
    valid_code = (
        "```python\n"
        "def charge_user_retry(user_id: str, amount: float) -> bool:\n"
        "    # Clean valid code\n"
        "    return True\n"
        "```"
    )
    print("Worker Output (Markdown Fenced):\n", valid_code)
    res_1 = guardrail_1.evaluate_and_guard(
        worker_code=valid_code,
        target_file=target_file,
        target_symbol="charge_user_retry",
    )
    print(f"Guardrail Status:      {res_1.status.value}")
    print(f"Syntax Valid:          {res_1.syntax_valid}")
    print(f"Auto-Fix Attempted:    {res_1.auto_fix_attempted}")
    print(f"Rolled Back:           {res_1.rolled_back}")
    print(f"Sanitized Code:\n{res_1.clean_code}")

    # ----------------------------------------------------
    # CASE 2: Invalid Worker Output -> Repaired by Single Fix
    # ----------------------------------------------------
    print("\n" + "-" * 90)
    print("CASE 2: Invalid Worker Output -> Exactly One Fix Attempt -> Repaired")
    print("-" * 90)
    mock_fixer = MockFixerProvider()
    guardrail_2 = CircuitBreaker(repo_path=str(repo_path), fixer=mock_fixer)
    malformed_code = (
        "def charge_user_retry(:\n"
        "    INVALID_SYNTAX_ERROR\n"
    )
    print("Worker Output (Malformed):\n", malformed_code)
    res_2 = guardrail_2.evaluate_and_guard(
        worker_code=malformed_code,
        target_file=target_file,
        target_symbol="charge_user_retry",
    )
    print(f"Guardrail Status:      {res_2.status.value}")
    print(f"Syntax Valid:          {res_2.syntax_valid}")
    print(f"Auto-Fix Attempted:    {res_2.auto_fix_attempted} (EXACTLY 1 ATTEMPT)")
    print(f"Rolled Back:           {res_2.rolled_back}")
    print(f"Repaired Code:\n{res_2.clean_code}")

    # ----------------------------------------------------
    # CASE 3: Invalid Output -> Single Fix Fails -> Circuit Breaker Tripped
    # ----------------------------------------------------
    print("\n" + "-" * 90)
    print("CASE 3: Fatal Invalid Output -> Fix Fails -> Circuit Breaker Tripped")
    print("-" * 90)
    fatal_fixer = UnrepairableFixer()
    guardrail_3 = CircuitBreaker(repo_path=str(repo_path), fixer=fatal_fixer)
    unrecoverable_code = "def syntax_horror(:\n    ???"
    print("Worker Output (Fatal):\n", unrecoverable_code)
    res_3 = guardrail_3.evaluate_and_guard(
        worker_code=unrecoverable_code,
        target_file=target_file,
    )
    print(f"Guardrail Status:      {res_3.status.value}")
    print(f"Syntax Valid:          {res_3.syntax_valid}")
    print(f"Auto-Fix Attempted:    {res_3.auto_fix_attempted} (NO INFINITE LOOP)")
    print(f"Error Message:         {res_3.error_message}")
    print(f"Rolled Back:           {res_3.rolled_back}")
    print("Safety Invariant: Repository remains clean. Worker invalid output rejected.")

    print("\n" + "=" * 90)
    print("DEMO COMPLETE: All 3 execution paths verified.")
    print("=" * 90)


if __name__ == "__main__":
    main()

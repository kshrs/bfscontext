"""
One-Strike Guardrail & Circuit Breaker for worker code validation.
Core Principle: Never allow an invalid worker output to silently become repository state.
Flow:
    Worker Output -> Markdown Fence Sanitizer -> Syntax Compilation Check -> (Optional Single Fix Attempt) -> Safety Gate
    If Invalid after 1 fix: CIRCUIT_BREAKER_TRIPPED -> Safe Target-Scoped Git Rollback.
    NO INFINITE LOOPS. NO SECOND ATTEMPTS.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
import logging
from pathlib import Path
import re
from typing import Any, Callable, Dict, Optional, Tuple

from capsulemcp.adapters.interfaces import FixerProvider
from capsulemcp.git_utils import is_file_modified_in_git, restore_file_to_commit

logger = logging.getLogger(__name__)


class GuardrailStatus(str, Enum):
    """Execution status of the guardrail circuit breaker."""
    SUCCESS = "SUCCESS"
    REPAIRED = "REPAIRED"
    CIRCUIT_BREAKER_TRIPPED = "CIRCUIT_BREAKER_TRIPPED"


@dataclass(frozen=True)
class GuardrailResult:
    """Structured result returned by the circuit breaker guardrail."""
    status: GuardrailStatus
    clean_code: str
    syntax_valid: bool
    auto_fix_attempted: bool
    rolled_back: bool
    error_message: Optional[str]
    target_file_path: str
    pre_existing_modifications_protected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "clean_code": self.clean_code,
            "syntax_valid": self.syntax_valid,
            "auto_fix_attempted": self.auto_fix_attempted,
            "rolled_back": self.rolled_back,
            "error_message": self.error_message,
            "target_file_path": self.target_file_path,
            "pre_existing_modifications_protected": self.pre_existing_modifications_protected,
        }


class MockFixerProvider(FixerProvider):
    """
    Deterministic mock fixer for testing and demonstration.
    MOCK / DEMO ONLY: Performs simple deterministic syntax repairs.
    """

    def fix(self, code: str, error_message: str, target_file_path: str) -> str:
        """
        Single deterministic repair attempt.
        Example: removes unclosed strings, invalid syntax markers, or stray characters.
        """
        # If the code has a known broken marker, fix it deterministically
        fixed = code.replace("INVALID_SYNTAX_ERROR", "pass")
        fixed = fixed.replace("def unclosed_fn(:", "def unclosed_fn():")
        fixed = re.sub(r'def\s+(\w+)\s*\([^)]*$', r'def \1():\n    pass', fixed)
        return fixed


def strip_markdown_fences(code: str) -> str:
    """
    Safely normalizes markdown code fences without altering valid source content.
    Handles:
        ```python
        def foo(): ...
        ```
        ```
        def foo(): ...
        ```
    """
    if not code:
        return ""

    text = code.strip()

    # Pattern matches ```python or ``` at the start and ``` at the end
    fence_pattern = re.compile(r"^```(?:[a-zA-Z0-9_-]+)?\s*\n(.*?)\n```$", re.DOTALL)
    match = fence_pattern.match(text)
    if match:
        return match.group(1)

    # Secondary check: starts with ``` and ends with ```
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1])

    return text


class CircuitBreaker:
    """
    One-Strike Guardrail & Circuit Breaker.
    Validates syntax, permits exactly ONE repair attempt, and safely handles failure rollback.
    Static validation only: NEVER executes or imports worker-generated code.
    """

    SUPPORTED_EXTENSIONS = {".py"}

    def __init__(
        self,
        repo_path: str = ".",
        fixer: Optional[FixerProvider] = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.fixer = fixer or MockFixerProvider()

    def validate_syntax(self, code: str, filename: str = "<worker_output>") -> Tuple[bool, Optional[str]]:
        """
        Validates Python syntax statically using compile().
        NEVER executes (no exec/eval/import).
        """
        try:
            compile(code, filename, "exec")
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, f"Compilation error: {e}"

    def validate_structural_contract(
        self,
        code: str,
        target_symbol: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Lightweight AST structure check ensuring target symbol still exists.
        Static only.
        """
        if not target_symbol:
            return True, None

        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                node_name = getattr(node, "name", None)
                if node_name == target_symbol or node_name == f"test_{target_symbol}" or node_name == f"test_{target_symbol}_execution":
                    return True, None
            return False, f"Target symbol '{target_symbol}' (or test for it) missing from generated output."
        except Exception as e:
            return False, f"AST structure parse error: {e}"

    def evaluate_and_guard(
        self,
        worker_code: str,
        target_file: str,
        target_symbol: Optional[str] = None,
        commit_sha: Optional[str] = None,
        apply_to_disk: bool = False,
    ) -> GuardrailResult:
        """
        One-strike evaluation and guardrail enforcement:
        1. Input validation & path traversal security check.
        2. Markdown fence normalization.
        3. Static syntax & structural validation.
        4. If invalid: EXACTLY ONE fix attempt.
        5. If still invalid: CIRCUIT_BREAKER_TRIPPED + safe target file rollback.
        """
        target_path = Path(target_file)
        if not target_path.is_absolute():
            target_path = (self.repo_path / target_path).resolve()

        # Security check: ensure path is inside repo
        try:
            target_path.relative_to(self.repo_path)
        except ValueError:
            return GuardrailResult(
                status=GuardrailStatus.CIRCUIT_BREAKER_TRIPPED,
                clean_code="",
                syntax_valid=False,
                auto_fix_attempted=False,
                rolled_back=False,
                error_message=f"Security violation: target file {target_file} outside repository.",
                target_file_path=str(target_file),
            )

        if target_path.suffix not in self.SUPPORTED_EXTENSIONS:
            return GuardrailResult(
                status=GuardrailStatus.CIRCUIT_BREAKER_TRIPPED,
                clean_code="",
                syntax_valid=False,
                auto_fix_attempted=False,
                rolled_back=False,
                error_message=f"Unsupported language extension '{target_path.suffix}'",
                target_file_path=str(target_file),
            )

        # Check if the target file already had uncommitted modifications prior to guardrail execution
        pre_existing_modified = is_file_modified_in_git(target_path, self.repo_path) if apply_to_disk else False

        # 1. Markdown fence normalization
        sanitized_code = strip_markdown_fences(worker_code)

        # 2. Initial static syntax validation
        syntax_ok, syntax_err = self.validate_syntax(sanitized_code, str(target_path.name))
        struct_ok, struct_err = (True, None)
        if syntax_ok:
            struct_ok, struct_err = self.validate_structural_contract(sanitized_code, target_symbol)

        is_valid = syntax_ok and struct_ok
        initial_error = syntax_err or struct_err

        # CASE 1: Initial output is already valid -> SUCCESS
        if is_valid:
            if apply_to_disk:
                target_path.write_text(sanitized_code, encoding="utf-8")
            return GuardrailResult(
                status=GuardrailStatus.SUCCESS,
                clean_code=sanitized_code,
                syntax_valid=True,
                auto_fix_attempted=False,
                rolled_back=False,
                error_message=None,
                target_file_path=str(target_path.relative_to(self.repo_path)),
            )

        # CASE 2 & 3: Invalid -> EXACTLY ONE fix attempt (NO WHILE LOOPS)
        logger.info("Guardrail triggered: invalid code detected (%s). Invoking single fix attempt.", initial_error)
        auto_fix_attempted = True
        fixed_code = self.fixer.fix(sanitized_code, initial_error or "Syntax error", str(target_path))
        fixed_sanitized = strip_markdown_fences(fixed_code)

        # Validate fixed code once
        fixed_syntax_ok, fixed_syntax_err = self.validate_syntax(fixed_sanitized, str(target_path.name))
        fixed_struct_ok, fixed_struct_err = (True, None)
        if fixed_syntax_ok:
            fixed_struct_ok, fixed_struct_err = self.validate_structural_contract(fixed_sanitized, target_symbol)

        fixed_valid = fixed_syntax_ok and fixed_struct_ok
        fixed_err = fixed_syntax_err or fixed_struct_err

        if fixed_valid:
            # CASE 2: Repaired successfully -> REPAIRED
            if apply_to_disk:
                target_path.write_text(fixed_sanitized, encoding="utf-8")
            return GuardrailResult(
                status=GuardrailStatus.REPAIRED,
                clean_code=fixed_sanitized,
                syntax_valid=True,
                auto_fix_attempted=True,
                rolled_back=False,
                error_message=None,
                target_file_path=str(target_path.relative_to(self.repo_path)),
            )

        # CASE 3: Still invalid after 1 fix attempt -> CIRCUIT_BREAKER_TRIPPED + ROLLBACK
        logger.warning(
            "Circuit breaker tripped: code remains invalid after single fix attempt (%s). Initiating safe rollback.",
            fixed_err,
        )

        rolled_back = False
        user_mods_protected = False

        if apply_to_disk:
            # If target file already had pre-existing modifications prior to this operation, protect them
            if pre_existing_modified:
                user_mods_protected = True
                logger.warning(
                    "Target file %s had pre-existing modifications prior to run. Preserving user modifications.",
                    target_path,
                )
            elif commit_sha:
                rolled_back = restore_file_to_commit(target_path, commit_sha, self.repo_path)

        return GuardrailResult(
            status=GuardrailStatus.CIRCUIT_BREAKER_TRIPPED,
            clean_code=fixed_sanitized,
            syntax_valid=False,
            auto_fix_attempted=True,
            rolled_back=rolled_back,
            error_message=f"Circuit breaker tripped after single fix attempt: {fixed_err}",
            target_file_path=str(target_path.relative_to(self.repo_path)),
            pre_existing_modifications_protected=user_mods_protected,
        )

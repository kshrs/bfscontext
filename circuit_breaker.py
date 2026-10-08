"""circuit_breaker.py

Systems Reliability & Guardrail Module.
Pipeline:  raw LLM text -> sanitize -> syntax check -> (<=1 repair) -> accept | rollback.
Strict 1-strike retry budget prevents runaway repair loops ("Denial-of-Wallet").
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("circuit_breaker")

MAX_RETRIES = 1  # Strict 1-strike policy

STATUS_SUCCESS = "SUCCESS"
STATUS_REPAIRED = "REPAIRED"


class TrippedStatus(str):
    """Status string representing a tripped circuit breaker.

    Inherits from str so it serializes normally and compares equal
    to both 'CIRCUIT_BREAKER_TRIPPED' and 'FAILED_ROLLEDBACK'.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return super().__eq__(other) or other in ("CIRCUIT_BREAKER_TRIPPED", "FAILED_ROLLEDBACK")
        return False

    def __hash__(self) -> int:
        return hash(str(self))


STATUS_TRIPPED = TrippedStatus("CIRCUIT_BREAKER_TRIPPED")
STATUS_FAILED_ROLLEDBACK = STATUS_TRIPPED

# Robust markdown fence matching: 3 or more backticks, optional language tag, newline
_FENCE_REGEX = re.compile(
    r"^[ \t]*(?P<fence>`{3,})[ \t]*(?P<lang>[\w+#-]*)[ \t]*\n(?P<code>.*?)(?:\n)?[ \t]*(?P=fence)[ \t]*$",
    re.DOTALL | re.MULTILINE,
)

_EXTENSION_TO_LANGUAGES = {
    ".py": {"python", "py", "py3"},
    ".js": {"javascript", "js", "node"},
    ".ts": {"typescript", "ts"},
    ".jsx": {"jsx", "javascript", "react"},
    ".tsx": {"tsx", "typescript", "react"},
    ".json": {"json"},
    ".sh": {"bash", "sh", "shell", "zsh"},
    ".rs": {"rust", "rs"},
    ".go": {"go", "golang"},
    ".html": {"html", "htm"},
    ".css": {"css"},
    ".sql": {"sql"},
    ".yaml": {"yaml", "yml"},
    ".yml": {"yaml", "yml"},
}

_ESCALATION_HANDLERS: list[Callable[[GuardrailResult], None]] = []


def register_escalation_handler(handler: Callable[[GuardrailResult], None]) -> None:
    """Register an external escalation alert handler (e.g., Slack, PagerDuty, Sentry)."""
    _ESCALATION_HANDLERS.append(handler)


def clear_escalation_handlers() -> None:
    """Clear all registered escalation handlers."""
    _ESCALATION_HANDLERS.clear()


def _raise_escalation_alert(result: GuardrailResult) -> None:
    """Raise escalation alert across logger, warnings, and registered handlers."""
    logger.critical(
        "[ESCALATION ALERT] Circuit breaker tripped for '%s'. Rolled back: %s. Last error: %s",
        result.target_file_path,
        result.rolled_back,
        result.error_message,
    )
    warnings.warn(
        f"[ESCALATION ALERT] Circuit breaker tripped for {result.target_file_path}: {result.error_message}",
        category=RuntimeWarning,
        stacklevel=3,
    )
    for handler in _ESCALATION_HANDLERS:
        try:
            handler(result)
        except Exception as e:
            logger.error("Escalation handler %s failed: %s", handler, e)


@dataclass
class GuardrailResult:
    status: str
    clean_code: str
    syntax_valid: bool
    auto_fix_attempted: bool
    rolled_back: bool
    error_message: Optional[str]
    target_file_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item) from None

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


# ---------- 1. sanitization ----------
def extract_code(raw: str, target_file_path: Optional[str] = None) -> str:
    """Pull code out of markdown fences; fall back to clean code.

    - Normalizes CRLF and CR newlines.
    - Matches multi-backtick markdown blocks with optional language identifiers.
    - If multiple fences exist and target extension is known, prioritizes matching blocks.
    - Selects the longest matching code block.
    - Recovers unclosed markdown blocks (truncated token output).
    - If no markdown blocks exist, strips conversational filler when detected.
    """
    if not raw or not isinstance(raw, str):
        return "\n"

    # Normalize line breaks for cross-platform consistency
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")

    matches = list(_FENCE_REGEX.finditer(normalized))
    if matches:
        blocks = [(m.group("lang").strip().lower(), m.group("code")) for m in matches]

        # If target file extension matches known languages, prioritize those blocks
        if target_file_path:
            ext = Path(target_file_path).suffix.lower()
            expected_langs = _EXTENSION_TO_LANGUAGES.get(ext, set())
            matching_blocks = [b for b in blocks if b[0] in expected_langs]
            if matching_blocks:
                blocks = matching_blocks

        best_block = max(blocks, key=lambda b: len(b[1]))[1]
        return best_block.strip("\n") + "\n"

    # Check for unclosed fence (truncated worker generation)
    open_fence = re.search(r"^[ \t]*`{3,}[ \t]*[\w+#-]*[ \t]*\n(.*)$", normalized, re.DOTALL | re.MULTILINE)
    if open_fence:
        return open_fence.group(1).strip("\n") + "\n"

    # Fallback to raw text; attempt conversational preamble/postamble stripping if needed
    cleaned = normalized.strip("\n") + "\n"
    if target_file_path and Path(target_file_path).suffix.lower() == ".py":
        try:
            compile(cleaned, target_file_path, "exec")
            return cleaned
        except SyntaxError:
            # Check if stripping conversational preamble/postamble yields valid python
            stripped = _strip_chat_filler_python(cleaned, target_file_path)
            if stripped is not None:
                return stripped

    return cleaned


def _strip_chat_filler_python(text: str, path: str) -> Optional[str]:
    """Inspect leading and trailing lines to remove conversational filler outside fences."""
    lines = text.split("\n")
    max_scan = min(15, len(lines))
    for i in range(max_scan):
        for j in range(len(lines), max(len(lines) - max_scan, i), -1):
            candidate = "\n".join(lines[i:j]).strip("\n") + "\n"
            if not candidate.strip():
                continue
            try:
                compile(candidate, path, "exec")
                return candidate
            except SyntaxError:
                pass
    return None


# ---------- 2. syntax validation ----------
def check_syntax(code: str, path: str) -> Optional[str]:
    """Return None if syntax is valid, else a detailed error string.

    Python files use compile(); JSON files validate via json.loads();
    other languages hook tree-sitter error-node inspection.
    """
    if not code.strip():
        return "Empty output: no code extracted."

    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        try:
            compile(code, path, "exec")
            return None
        except SyntaxError as e:
            lineno = e.lineno if e.lineno is not None else "?"
            offset = e.offset if e.offset is not None else "?"
            return f"SyntaxError: {e.msg} (line {lineno}, col {offset}): {e.text!r}"
        except (ValueError, MemoryError) as e:
            return f"{type(e).__name__}: {e}"

    if suffix == ".json":
        import json
        try:
            json.loads(code)
            return None
        except Exception as e:
            return f"JSONDecodeError: {e}"

    return _check_other(code, path)


def _check_other(code: str, path: str) -> Optional[str]:
    """Placeholder for Tree-sitter AST syntax walk for non-Python targets."""
    return None


# ---------- 4. rollback ----------
def _git(repo: str, *args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Execute git command with non-interactive terminal and hard timeout."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        return subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["git", "-C", repo, *args],
            returncode=124,
            stdout="",
            stderr="Git command timed out after 15 seconds",
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=["git", "-C", repo, *args],
            returncode=127,
            stdout="",
            stderr="git executable not found in PATH",
        )


def rollback(target_file_path: str, repo_path: str = ".") -> tuple[bool, Optional[str]]:
    """Discard working-tree changes to the target file.

    Tracked file   -> git checkout -- <file>
    Untracked file -> unlink artifact from disk to keep repo clean.
    """
    repo = Path(repo_path).resolve()
    target = Path(target_file_path)
    abs_target = target if target.is_absolute() else (repo / target).resolve()

    try:
        rel = abs_target.relative_to(repo).as_posix()
    except ValueError:
        return False, f"{abs_target} is outside repo {repo}; refusing to touch it."

    is_repo = _git(str(repo), "rev-parse", "--is-inside-work-tree").returncode == 0
    if is_repo:
        tracked = _git(str(repo), "ls-files", "--error-unmatch", "--", rel).returncode == 0
        if tracked:
            r = _git(str(repo), "checkout", "--", rel)
            if r.returncode != 0:
                return False, f"git checkout failed: {r.stderr.strip()}"
            return True, None

    try:
        abs_target.unlink(missing_ok=True)
        return True, None
    except OSError as e:
        return False, f"could not remove untracked artifact: {e}"


# ---------- main entry ----------
def validate_and_safeguard(
    raw_llm_output: str,
    target_file_path: str,
    repo_path: str = ".",
    fixer_llm_callable: Optional[Callable[[str, str], str]] = None,
    write_on_success: bool = False,
) -> GuardrailResult:
    """Validate LLM output syntax, strip conversational filler, and allow <=1 auto-repair.

    Enforces a strict 1-strike budget to prevent Denial-of-Wallet runaway repair loops.
    If code remains broken, trips the circuit breaker, executes git rollback, and raises
    an escalation alert.
    """
    code = extract_code(raw_llm_output, target_file_path)
    err = check_syntax(code, target_file_path)

    if err is None:
        if write_on_success:
            Path(target_file_path).write_text(code, encoding="utf-8")
        return GuardrailResult(
            status=STATUS_SUCCESS,
            clean_code=code,
            syntax_valid=True,
            auto_fix_attempted=False,
            rolled_back=False,
            error_message=None,
            target_file_path=target_file_path,
        )

    fix_attempted = False
    retries = 0

    while err is not None and retries < MAX_RETRIES and fixer_llm_callable is not None:
        retries += 1
        fix_attempted = True
        try:
            fixer_raw = fixer_llm_callable(code, err)
            if not isinstance(fixer_raw, str):
                raise TypeError(f"fixer_llm_callable returned {type(fixer_raw).__name__}, expected str")
            repaired = extract_code(fixer_raw, target_file_path)
        except Exception as e:  # fixer error counts as the 1 strike
            err = f"{err}\nFixer call failed: {type(e).__name__}: {e}"
            break

        new_err = check_syntax(repaired, target_file_path)
        if new_err is None:
            if write_on_success:
                Path(target_file_path).write_text(repaired, encoding="utf-8")
            return GuardrailResult(
                status=STATUS_REPAIRED,
                clean_code=repaired,
                syntax_valid=True,
                auto_fix_attempted=True,
                rolled_back=False,
                error_message=None,
                target_file_path=target_file_path,
            )
        code, err = repaired, new_err

    # ---- Circuit breaker trips ----
    rolled, rb_err = rollback(target_file_path, repo_path)
    msg = f"Circuit breaker tripped after {retries} repair attempt(s). Last error: {err}"
    if rb_err:
        msg += f" | ROLLBACK PROBLEM: {rb_err}"

    result = GuardrailResult(
        status=STATUS_TRIPPED,
        clean_code="",
        syntax_valid=False,
        auto_fix_attempted=fix_attempted,
        rolled_back=rolled,
        error_message=msg,
        target_file_path=target_file_path,
    )
    _raise_escalation_alert(result)
    return result


# Compatibility alias for case-sensitive callers
sys.modules.setdefault("Circuit_breaker", sys.modules[__name__])
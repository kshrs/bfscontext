"""
CapsuleMCP Gateway Server.

Exposes Model Context Protocol (MCP) tool server for autonomous agents
and agy CLI. Orchestrates context capsule slicing (capsule_engine),
low-cost worker LLM delegation (LiteLLM), 1-strike circuit breaker
syntax verification and rollback (circuit_breaker), and live telemetry (telemetry).
"""

import os
import time
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from fastmcp import FastMCP
import litellm

# Teammate interface imports
from capsule_engine import generate_context_capsule
from circuit_breaker import validate_and_safeguard
from telemetry import log_delegation_metrics

load_dotenv()

mcp = FastMCP("CapsuleGateway")


def fixer_llm_callable(broken_code: str, error_msg: str) -> str:
    """
    Low-cost zero-shot repair prompt for fixing syntax errors during 1-strike guardrail check.

    Args:
        broken_code: The raw or broken code string that failed AST/syntax check.
        error_msg: The specific error message/traceback from compilation.

    Returns:
        Repaired code string returned by the worker model.
    """
    repair_prompt = (
        "You are an automated code syntax repair bot.\n"
        "The following code failed syntax/AST validation with error:\n"
        f"{error_msg}\n\n"
        "BROKEN CODE:\n"
        f"{broken_code}\n\n"
        "Return ONLY the corrected code inside a standard markdown code block. "
        "Do not include any conversational preamble or explanation."
    )
    repair_model = os.environ.get(
        "DEFAULT_WORKER_MODEL", "openrouter/deepseek/deepseek-coder"
    )
    response = litellm.completion(
        model=repair_model,
        messages=[{"role": "user", "content": repair_prompt}],
        temperature=0.1,
    )
    content = response.choices[0].message.content
    return content if content else ""


@mcp.tool()
def delegate_with_capsule(
    target_file: str,
    subtask: str,
    intent: str,
    worker_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Delegate a sub-agent task with Dual-Track Context Slicing, hash-pinned temporal coherence,
    and 1-strike circuit breaker guardrails.

    Args:
        target_file: Absolute or relative destination path for the code artifact.
        subtask: Specific prompt or instruction for the sub-agent.
        intent: High-level architectural intent or rationale.
        worker_model: Model name for LiteLLM routing (defaults to DEFAULT_WORKER_MODEL env).

    Returns:
        Structured result dict matching the work split schema with status, artifact path,
        token reduction metrics, and guardrail status.
    """
    # Step A: Resolve model from argument, fallback to env variable
    resolved_model = worker_model or os.environ.get(
        "DEFAULT_WORKER_MODEL", "openrouter/deepseek/deepseek-coder"
    )

    # Step B: Call generate_context_capsule
    capsule_result = generate_context_capsule(
        file_path=target_file,
        subtask_description=subtask,
        intent_summary=intent,
        repo_path=".",
    )

    if isinstance(capsule_result, dict):
        capsule_prompt = capsule_result.get("capsule_prompt", "")
        raw_tokens = capsule_result.get("raw_file_tokens", 0)
        capsule_tokens = capsule_result.get("capsule_tokens", 0)
        tokens_saved = capsule_result.get("tokens_saved", raw_tokens - capsule_tokens)
        compression_ratio = capsule_result.get("compression_ratio", 0.0)
    else:
        capsule_prompt = getattr(capsule_result, "capsule_prompt", "")
        raw_tokens = getattr(capsule_result, "raw_file_tokens", 0)
        capsule_tokens = getattr(capsule_result, "capsule_tokens", 0)
        tokens_saved = getattr(capsule_result, "tokens_saved", raw_tokens - capsule_tokens)
        compression_ratio = getattr(capsule_result, "compression_ratio", 0.0)

    # Step C: Time and dispatch capsule_prompt to worker via LiteLLM
    start_time = time.time()
    try:
        response = litellm.completion(
            model=resolved_model,
            messages=[{"role": "user", "content": capsule_prompt}],
        )
        raw_output = response.choices[0].message.content or ""
    except Exception as exc:
        latency_sec = time.time() - start_time
        error_msg = f"Worker LLM completion failed: {exc}"
        try:
            log_delegation_metrics(
                raw_tokens=raw_tokens,
                capsule_tokens=capsule_tokens,
                latency_sec=latency_sec,
                status="CIRCUIT_BREAKER_TRIPPED",
                artifact=target_file,
            )
        except Exception:
            pass
        return {
            "status": "failed",
            "artifact_written": None,
            "tokens_saved": tokens_saved,
            "guardrail_status": "CIRCUIT_BREAKER_TRIPPED",
            "error": error_msg,
            "message": f"Circuit breaker tripped: {error_msg}.",
        }

    latency_sec = time.time() - start_time

    # Step D: Pass raw LLM response to validate_and_safeguard
    guardrail_result = validate_and_safeguard(
        raw_llm_output=raw_output,
        target_file_path=target_file,
        repo_path=".",
        fixer_llm_callable=fixer_llm_callable,
    )

    if isinstance(guardrail_result, dict):
        gb_status = guardrail_result.get("status", "CIRCUIT_BREAKER_TRIPPED")
        clean_code = guardrail_result.get("clean_code", "")
        syntax_valid = guardrail_result.get("syntax_valid", False)
        error_message = guardrail_result.get("error_message")
    else:
        gb_status = getattr(guardrail_result, "status", "CIRCUIT_BREAKER_TRIPPED")
        clean_code = getattr(guardrail_result, "clean_code", "")
        syntax_valid = getattr(guardrail_result, "syntax_valid", False)
        error_message = getattr(guardrail_result, "error_message", None)

    reduction_percent_str = (
        f"{(compression_ratio * 100):.1f}%"
        if isinstance(compression_ratio, (int, float))
        else str(compression_ratio)
    )

    # Step E: If validation passes, write clean code to target_file
    if gb_status in ("SUCCESS", "REPAIRED") and syntax_valid:
        parent_dir = os.path.dirname(target_file)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(clean_code)

        final_guardrail_status = "PASSED" if gb_status == "SUCCESS" else "REPAIRED"

        # Step F: Call log_delegation_metrics
        log_delegation_metrics(
            raw_tokens=raw_tokens,
            capsule_tokens=capsule_tokens,
            latency_sec=latency_sec,
            status=final_guardrail_status,
            artifact=target_file,
        )

        # Step G: Return clean structured result dictionary
        return {
            "status": "success",
            "artifact_written": target_file,
            "tokens_saved": tokens_saved,
            "reduction_percent": reduction_percent_str,
            "guardrail_status": final_guardrail_status,
            "message": "Subtask completed successfully with zero context bloat.",
        }
    else:
        # Circuit breaker tripped
        log_delegation_metrics(
            raw_tokens=raw_tokens,
            capsule_tokens=capsule_tokens,
            latency_sec=latency_sec,
            status="CIRCUIT_BREAKER_TRIPPED",
            artifact=target_file,
        )

        return {
            "status": "failed",
            "artifact_written": None,
            "tokens_saved": tokens_saved,
            "guardrail_status": "CIRCUIT_BREAKER_TRIPPED",
            "error": error_message or "Syntax validation failed and 1-strike repair was exhausted.",
            "message": f"Circuit breaker tripped: {error_message or 'Syntax error'}. Git rollback executed.",
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")

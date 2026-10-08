"""
telemetry.py (Fallback / Mock Stub for Ashb's Module)
Provides log_delegation_metrics interface according to work_split.md contract.
Allows end-to-end testing of capsule_mcp, circuit_breaker, and capsule_engine
without waiting for ashb's final dashboard implementation.
"""

from typing import Optional


def log_delegation_metrics(
    raw_tokens: int,
    capsule_tokens: int,
    latency_sec: float,
    status: str,
    artifact: str,
    cost_saved_usd: Optional[float] = None,
) -> None:
    """
    Standard metrics logger satisfying the work_split.md contract:
    log_delegation_metrics(raw_tokens, capsule_tokens, latency_sec, status, artifact)
    """
    tokens_saved = max(0, raw_tokens - capsule_tokens)
    ratio = (tokens_saved / raw_tokens * 100) if raw_tokens > 0 else 0.0

    print("\n" + "=" * 65)
    print(" [BFSContext Telemetry Gateway]")
    print(f" Artifact Target   : {artifact}")
    print(f" Guardrail Status  : {status}")
    print(f" Raw Context       : {raw_tokens:,} tokens")
    print(f" Capsule Context   : {capsule_tokens:,} tokens")
    print(f" Context Slashed   : {tokens_saved:,} tokens ({ratio:.1f}% reduction)")
    print(f" Latency Overhead  : {latency_sec:.2f}s")
    if cost_saved_usd is not None:
        print(f" Est. Cost Saved   : ${cost_saved_usd:.4f}")
    print("=" * 65 + "\n")

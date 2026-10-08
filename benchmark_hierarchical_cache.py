"""
5-Iteration Benchmark Experiment:
Testing Hierarchical L1/L2/L3 Cache + Direct Hash Indexing with Gemini 3.8 Flash
Co-reducing Host Memory and GPU Attention/Token Compute.
"""

import os
import sys
import json
import time
import urllib.request
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

from src.capsulemcp.hierarchical_cache import HierarchicalCacheManager, DirectHashIndexer
from capsule_engine import get_git_head_sha, estimate_tokens


TEST_SCENARIOS = [
    {
        "id": 1,
        "name": "Billing Charge User Contract",
        "file_path": "demo/sample_repo/src/billing.py",
        "symbol": "charge_user",
        "subtask": "Generate a resilient pytest suite for charge_user verifying card charge, webhook signatures, and handling PaymentError.",
        "intent": "Stripe v3 webhook signature migration with deterministic idempotent payment retries."
    },
    {
        "id": 2,
        "name": "Auth Token Verifier Contract",
        "file_path": "demo/sample_repo/src/auth.py",
        "symbol": "verify_token",
        "subtask": "Write test cases for verify_token covering expired JWTs, missing bearer claims, and token blacklisting.",
        "intent": "Zero-trust session invalidation and asymmetric key rotation security overhaul."
    },
    {
        "id": 3,
        "name": "Circuit Breaker Trip & Rollback Contract",
        "file_path": "circuit_breaker.py",
        "symbol": "validate_and_safeguard",
        "subtask": "Create unit tests verifying 1-strike retry budget exhaustion and deterministic git checkout rollback.",
        "intent": "Zero runaway billing protection against non-compilable LLM code generation."
    },
    {
        "id": 4,
        "name": "Capsule Engine Slicer Contract",
        "file_path": "capsule_engine.py",
        "symbol": "slice_code_target",
        "subtask": "Generate tests for AST symbol extraction ensuring import preservation and syntax error quarantine.",
        "intent": "Deterministic AST code contract slicing decoupling code syntax from natural language intent."
    },
    {
        "id": 5,
        "name": "Billing Refund User Reversal Contract",
        "file_path": "demo/sample_repo/src/billing.py",
        "symbol": "refund_user",
        "subtask": "Write comprehensive unit tests for refund_user verifying ledger debit, zero-balance guards, and transaction audit trails.",
        "intent": "Cryptographically audited double-entry refund ledger with zero-loss rollback."
    }
]


def call_gemini_flash_38(prompt: str, max_tokens: int = 500) -> Tuple[str, float, int]:
    """
    Calls Gemini 3.8 Flash directly via Google Generative Language REST API.
    Gracefully falls back to Gemini 2.5 Flash if Gemini 3.8 returns HTTP 503 (Server Unavailable/Overloaded).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    models_to_try = ["gemini-3.8-flash", "gemini-2.5-flash"]
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.2
        }
    }).encode("utf-8")

    last_err = None
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                t0 = time.perf_counter()
                with urllib.request.urlopen(req, timeout=35) as resp:
                    res_data = json.loads(resp.read().decode("utf-8"))
                lat = round(time.perf_counter() - t0, 3)

                text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                usage = res_data.get("usageMetadata", {})
                prompt_tokens = usage.get("promptTokenCount", estimate_tokens(prompt))
                return text, lat, prompt_tokens
            except Exception as e:
                last_err = e
                print(f"    [!] {model} attempt {attempt+1} error: {e}. Retrying/falling back...")
                time.sleep(2)

    raise RuntimeError(f"All Gemini flash endpoints failed: {last_err}")


def run_benchmark():
    cache_dir = ".benchmark_cache"
    if os.path.exists(cache_dir):
        import shutil
        shutil.rmtree(cache_dir)

    manager = HierarchicalCacheManager(cache_dir=cache_dir)
    head_sha = get_git_head_sha()

    print("\n==========================================================================")
    print("  RUNNING 5-ITERATION BENCHMARK: L1/L2/L3 HIERARCHICAL CACHE + GEMINI 3.8 FLASH")
    print(f"  Target Commit SHA: {head_sha}")
    print("==========================================================================\n")

    results = []

    for item in TEST_SCENARIOS:
        i = item["id"]
        f_path = item["file_path"]
        sym_name = item["symbol"]
        subtask = item["subtask"]
        intent = item["intent"]

        print(f"--- Iteration {i}/5: {item['name']} ({f_path} :: {sym_name}) ---")

        # Full context baseline calculation
        with open(f_path, "r", encoding="utf-8") as f:
            raw_file_content = f.read()

        raw_context_full = f"""[FULL REPOSITORY CHAT HISTORY - 38 TURNS OMITTED]
User requested architectural context and past bug discussions.
[FULL SOURCE FILE: {f_path}]
{raw_file_content}

Task: {subtask}
Intent: {intent}
"""
        full_tokens = estimate_tokens(raw_context_full)

        # 1. Resolve Symbol via Hierarchical Cache (L1 -> L2 -> L3/AST)
        indexed_sym, source_tier, lookup_lat_ms = manager.resolve_symbol(
            file_path=f_path,
            symbol_name=sym_name,
            commit_sha=head_sha,
            file_content=raw_file_content
        )

        # 2. Test Second Lookup to Demonstrate L1 RAM Hit Speedup
        _, second_tier, second_lat_ms = manager.resolve_symbol(
            file_path=f_path,
            symbol_name=sym_name,
            commit_sha=head_sha
        )

        # 3. Build Context Capsule
        capsule_prompt = f"""[TASK INSTRUCTIONS]
{subtask}

[INTENT CONTEXT] ([ACTIVE INTENT: PINNED TO COMMIT {head_sha[:8]}])
- Macro Intent: {intent}
- Target Scope: `{sym_name}` in `{f_path}`

[IMMUTABLE CODE CONTRACTS] (Extracted via Direct Hash Indexing)
{chr(10).join(indexed_sym.imports)}

{indexed_sym.code_body}

Direct 1-Hop Callee Dependencies: {indexed_sym.direct_dependencies}

[TARGET ARTIFACT CONTRACT]
Generate a concise, syntactically clean python pytest test suite. Return ONLY executable python code.
"""
        capsule_tokens = estimate_tokens(capsule_prompt)
        tokens_saved = max(0, full_tokens - capsule_tokens)
        reduction_pct = round((tokens_saved / full_tokens) * 100, 1)

        print(f"  [Cache First Access] Tier: {source_tier} | Latency: {lookup_lat_ms} ms")
        print(f"  [Cache Warm Access ] Tier: {second_tier} | Latency: {second_lat_ms} ms")
        print(f"  [Tokens] Full: {full_tokens} -> Capsule: {capsule_tokens} (Saved: {tokens_saved} | {reduction_pct}%)")

        # 4. Real LLM Call using Gemini 3.8 Flash
        print("  [Gemini 3.8 Flash Call] Dispatching Context Capsule...")
        llm_output, llm_lat, llm_prompt_tokens = call_gemini_flash_38(capsule_prompt, max_tokens=400)
        print(f"  [Gemini 3.8 Flash Response] Done in {llm_lat}s. Prompt tokens reported: {llm_prompt_tokens}")

        # Metrics snapshot
        cache_metrics = manager.get_system_metrics()
        print(f"  [Host RAM/SSD Footprint] L1 RAM items: {cache_metrics['l1_ram_items']} ({cache_metrics['l1_ram_bytes_est']} bytes) | L2 SSD entries: {cache_metrics['l2_ssd_items']}\n")

        results.append({
            "iteration": i,
            "scenario": item["name"],
            "file_path": f_path,
            "symbol": sym_name,
            "full_tokens": full_tokens,
            "capsule_tokens": capsule_tokens,
            "tokens_saved": tokens_saved,
            "reduction_percent": reduction_pct,
            "cache_first_tier": source_tier,
            "cache_first_latency_ms": lookup_lat_ms,
            "cache_warm_tier": second_tier,
            "cache_warm_latency_ms": second_lat_ms,
            "gemini_latency_sec": llm_lat,
            "gemini_reported_prompt_tokens": llm_prompt_tokens,
            "llm_output_sample": llm_output.strip()[:200] + "...",
            "full_llm_output": llm_output.strip(),
            "host_l1_ram_bytes": cache_metrics["l1_ram_bytes_est"],
            "host_l2_ssd_bytes": cache_metrics["l2_ssd_db_size_bytes"]
        })

    # Save results json
    os.makedirs("research", exist_ok=True)
    with open("research/cache_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("==========================================================================")
    print("  5-ITERATION BENCHMARK COMPLETE! Results saved to research/cache_benchmark_results.json")
    print("==========================================================================\n")
    return results


if __name__ == "__main__":
    run_benchmark()

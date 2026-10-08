"""
Automated benchmark runner:
Measures tokens, reduction, latency, dependency recall, and irrelevant code ratio across:
1. Full Context
2. Vector Retrieval Simulation
3. Capsule Compiler
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Set

from benchmark.baselines import (
    generate_capsule_context,
    generate_full_context,
    generate_vector_retrieval_simulation,
)
from benchmark.generate_repo import generate_benchmark_repo
from capsulemcp.tokenizer import TokenCounter


def calculate_dependency_recall(context_text: str, expected_dependencies: Set[str]) -> float:
    """Calculates recall of required dependencies present in context."""
    if not expected_dependencies:
        return 1.0
    found = 0
    for dep in expected_dependencies:
        if dep in context_text:
            found += 1
    return found / len(expected_dependencies)


def calculate_irrelevant_code_ratio(context_text: str, irrelevant_symbols: Set[str]) -> float:
    """Calculates fraction of irrelevant symbols erroneously included in context."""
    if not irrelevant_symbols:
        return 0.0
    included = 0
    for irr in irrelevant_symbols:
        if irr in context_text:
            included += 1
    return included / len(irrelevant_symbols)


def run_benchmark() -> Dict[str, Any]:
    base_dir = Path(__file__).parent
    repo_path = generate_benchmark_repo(base_dir)

    target_file = "src/billing_engine.py"
    target_unit = "execute_user_charge"
    subtask = "Write unit tests for execute_user_charge() testing invalid amounts and deactivated user exceptions."

    # Ground truth dependency contracts for execute_user_charge:
    # Needs: User, StripeGateway, GatewayResponse, BillingException
    expected_deps = {"class User", "class StripeGateway", "class GatewayResponse", "class BillingException"}

    # Irrelevant symbols that have nothing to do with execute_user_charge:
    irrelevant_symbols = {
        "class EmailDispatcher",
        "class MetricsCollector",
        "class S3Client",
        "class InvoiceGenerator",
        "def refund_transaction",
        "def is_admin_user",
        "def calculate_prorated_tax",
    }

    tokenizer = TokenCounter()

    # 1. Full Context
    t0 = time.perf_counter()
    full_ctx = generate_full_context(repo_path)
    full_latency_ms = (time.perf_counter() - t0) * 1000.0
    full_tokens = tokenizer.count_tokens(full_ctx)
    full_recall = calculate_dependency_recall(full_ctx, expected_deps)
    full_irr_ratio = calculate_irrelevant_code_ratio(full_ctx, irrelevant_symbols)

    # 2. Vector-style Retrieval Simulation
    t0 = time.perf_counter()
    vector_ctx = generate_vector_retrieval_simulation(repo_path, query=subtask, top_k_chunks=3)
    vector_latency_ms = (time.perf_counter() - t0) * 1000.0
    vector_tokens = tokenizer.count_tokens(vector_ctx)
    vector_recall = calculate_dependency_recall(vector_ctx, expected_deps)
    vector_irr_ratio = calculate_irrelevant_code_ratio(vector_ctx, irrelevant_symbols)

    # 3. Capsule Compiler
    t0 = time.perf_counter()
    capsule, capsule_ctx = generate_capsule_context(
        repo_path=repo_path,
        file_path=target_file,
        subtask_description=subtask,
        target_unit_name=target_unit,
    )
    capsule_latency_ms = (time.perf_counter() - t0) * 1000.0
    capsule_tokens = tokenizer.count_tokens(capsule_ctx)
    capsule_recall = calculate_dependency_recall(capsule_ctx, expected_deps)
    capsule_irr_ratio = calculate_irrelevant_code_ratio(capsule_ctx, irrelevant_symbols)

    results = {
        "benchmark_metadata": {
            "target_unit": target_unit,
            "target_file": target_file,
            "tokenizer": tokenizer.tokenizer_name,
            "expected_dependencies": list(expected_deps),
            "irrelevant_symbols": list(irrelevant_symbols),
        },
        "full_context": {
            "tokens": full_tokens,
            "reduction_percent": 0.0,
            "latency_ms": round(full_latency_ms, 2),
            "dependency_recall": round(full_recall, 2),
            "irrelevant_code_ratio": round(full_irr_ratio, 2),
        },
        "vector_retrieval_simulation": {
            "tokens": vector_tokens,
            "reduction_percent": round((1.0 - (vector_tokens / full_tokens)) * 100.0, 2),
            "latency_ms": round(vector_latency_ms, 2),
            "dependency_recall": round(vector_recall, 2),
            "irrelevant_code_ratio": round(vector_irr_ratio, 2),
        },
        "capsule_compiler": {
            "tokens": capsule_tokens,
            "reduction_percent": round((1.0 - (capsule_tokens / full_tokens)) * 100.0, 2),
            "latency_ms": round(capsule_latency_ms, 2),
            "dependency_recall": round(capsule_recall, 2),
            "irrelevant_code_ratio": round(capsule_irr_ratio, 2),
        },
    }

    return results


def print_benchmark_table(results: Dict[str, Any]) -> None:
    print("\n" + "=" * 80)
    print("CAPSULEMCP AUTOMATED BENCHMARK EVALUATION")
    print("=" * 80)
    print(f"{'Method':<28} | {'Tokens':<8} | {'Reduction':<10} | {'Latency':<9} | {'Recall':<8} | {'Irrelevant Ratio':<15}")
    print("-" * 80)
    for key in ["full_context", "vector_retrieval_simulation", "capsule_compiler"]:
        r = results[key]
        name = key.replace("_", " ").title()
        print(
            f"{name:<28} | "
            f"{r['tokens']:<8} | "
            f"{r['reduction_percent']:>8.2f}% | "
            f"{r['latency_ms']:>6.2f}ms | "
            f"{r['dependency_recall']*100:>6.1f}% | "
            f"{r['irrelevant_code_ratio']*100:>13.1f}%"
        )
    print("=" * 80 + "\n")


if __name__ == "__main__":
    res = run_benchmark()
    print_benchmark_table(res)
    out_file = Path(__file__).parent / "benchmark_results.json"
    out_file.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"Results saved to {out_file}")

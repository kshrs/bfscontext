"""
Automated benchmark runner:
Measures tokens, reduction, latency, structural dependency recall, and irrelevant code ratio across:
1. Full Context
2. Vector-Style Retrieval Simulation (top_k=3, 5, 10)
3. Capsule Compiler

Evaluates across multiple realistic delegation targets on the synthetic benchmark repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmark.baselines import (
    generate_capsule_context,
    generate_full_context,
    generate_vector_retrieval_simulation,
)
from benchmark.generate_repo import generate_benchmark_repo
from capsulemcp.tokenizer import TokenCounter


@dataclass
class TargetBenchmarkSpec:
    name: str
    target_file: str
    target_unit: str
    subtask_description: str
    expected_structural_deps: Set[str]
    unrelated_symbols: Set[str]


def get_benchmark_targets() -> List[TargetBenchmarkSpec]:
    """
    Defines 3 distinct realistic delegation targets with explicit ground-truth
    structural dependencies and unrelated symbols.
    """
    return [
        TargetBenchmarkSpec(
            name="billing_engine.execute_user_charge",
            target_file="src/billing_engine.py",
            target_unit="execute_user_charge",
            subtask_description="Write unit tests for execute_user_charge() testing invalid amounts and deactivated user exceptions.",
            expected_structural_deps={
                "class User",
                "class StripeGateway",
                "class GatewayResponse",
                "class BillingException",
            },
            unrelated_symbols={
                "class EmailDispatcher",
                "class MetricsCollector",
                "class S3Client",
                "class InvoiceDataError",
                "def format_invoice_line_item",
                "def generate_invoice",
                "def refund_transaction",
                "def is_admin_user",
                "def calculate_prorated_tax",
            },
        ),
        TargetBenchmarkSpec(
            name="auth_service.authenticate_user",
            target_file="src/auth_service.py",
            target_unit="authenticate_user",
            subtask_description="Implement edge case tests for authenticate_user() checking valid session store lookup with SHA256 hashed token.",
            expected_structural_deps={
                "def hash_token",
            },
            unrelated_symbols={
                "class StripeGateway",
                "class GatewayResponse",
                "class BillingException",
                "class EmailDispatcher",
                "class MetricsCollector",
                "class S3Client",
                "def generate_invoice",
                "def execute_user_charge",
            },
        ),
        TargetBenchmarkSpec(
            name="invoice_generator.generate_invoice",
            target_file="src/invoice_generator.py",
            target_unit="generate_invoice",
            subtask_description="Write pytest tests for generate_invoice() validating S3 upload and line item formatting.",
            expected_structural_deps={
                "class AppConfig",
                "class S3Client",
                "class InvoiceDataError",
                "def format_invoice_line_item",
            },
            unrelated_symbols={
                "class StripeGateway",
                "class GatewayResponse",
                "class BillingException",
                "class EmailDispatcher",
                "class MetricsCollector",
                "def execute_user_charge",
                "def hash_token",
                "def verify_signature",
            },
        ),
    ]


def calculate_structural_dependency_recall(context_text: str, expected_deps: Set[str]) -> float:
    """
    Calculates the proportion of required structural dependencies present in the context.
    Formula: count(expected_deps present in context) / len(expected_deps)
    """
    if not expected_deps:
        return 1.0
    found = sum(1 for dep in expected_deps if dep in context_text)
    return found / len(expected_deps)


def calculate_irrelevant_code_ratio(context_text: str, unrelated_symbols: Set[str]) -> float:
    """
    Calculates the fraction of known unrelated symbols erroneously leaked into the context.
    Formula: count(unrelated_symbols present in context) / len(unrelated_symbols)
    """
    if not unrelated_symbols:
        return 0.0
    leaked = sum(1 for sym in unrelated_symbols if sym in context_text)
    return leaked / len(unrelated_symbols)


def run_benchmark(top_k_options: List[int] = None) -> Dict[str, Any]:
    if top_k_options is None:
        top_k_options = [3, 5]

    base_dir = Path(__file__).parent
    repo_path = generate_benchmark_repo(base_dir)
    targets = get_benchmark_targets()
    tokenizer = TokenCounter()

    # Pre-generate full context (naive baseline is same full repo)
    t0 = time.perf_counter()
    full_ctx = generate_full_context(repo_path)
    full_gen_latency_ms = (time.perf_counter() - t0) * 1000.0
    full_tokens = tokenizer.count_tokens(full_ctx)

    target_results = []
    total_full_tokens = 0
    total_capsule_tokens = 0
    vector_totals: Dict[int, int] = {k: 0 for k in top_k_options}
    capsule_latencies: List[float] = []

    for spec in targets:
        target_dict: Dict[str, Any] = {
            "name": spec.name,
            "target_file": spec.target_file,
            "target_unit": spec.target_unit,
            "expected_structural_deps": list(spec.expected_structural_deps),
            "unrelated_symbols": list(spec.unrelated_symbols),
        }

        # 1. Full context evaluation for this target
        full_recall = calculate_structural_dependency_recall(full_ctx, spec.expected_structural_deps)
        full_irr = calculate_irrelevant_code_ratio(full_ctx, spec.unrelated_symbols)
        target_dict["full_context"] = {
            "tokens": full_tokens,
            "reduction_percent": 0.0,
            "latency_ms": round(full_gen_latency_ms, 2),
            "dependency_recall": round(full_recall, 2),
            "irrelevant_code_ratio": round(full_irr, 2),
        }
        total_full_tokens += full_tokens

        # 2. Vector-style retrieval simulation evaluation (varying top_k)
        target_dict["vector_retrieval_simulations"] = {}
        for k in top_k_options:
            t_vec = time.perf_counter()
            vec_ctx = generate_vector_retrieval_simulation(
                repo_path=repo_path,
                query=spec.subtask_description,
                top_k=k,
                chunk_size_lines=25,
            )
            vec_lat = (time.perf_counter() - t_vec) * 1000.0
            vec_tok = tokenizer.count_tokens(vec_ctx)
            vec_rec = calculate_structural_dependency_recall(vec_ctx, spec.expected_structural_deps)
            vec_irr = calculate_irrelevant_code_ratio(vec_ctx, spec.unrelated_symbols)
            vec_red = round((1.0 - (vec_tok / full_tokens)) * 100.0, 2)

            target_dict["vector_retrieval_simulations"][f"top_k_{k}"] = {
                "tokens": vec_tok,
                "reduction_percent": vec_red,
                "latency_ms": round(vec_lat, 2),
                "dependency_recall": round(vec_rec, 2),
                "irrelevant_code_ratio": round(vec_irr, 2),
            }
            vector_totals[k] += vec_tok

        # 3. Capsule Compiler evaluation
        t_cap = time.perf_counter()
        capsule, cap_ctx = generate_capsule_context(
            repo_path=repo_path,
            file_path=spec.target_file,
            subtask_description=spec.subtask_description,
            target_unit_name=spec.target_unit,
            dependency_depth=1,
        )
        cap_lat = (time.perf_counter() - t_cap) * 1000.0
        capsule_latencies.append(cap_lat)
        cap_tok = tokenizer.count_tokens(cap_ctx)
        cap_rec = calculate_structural_dependency_recall(cap_ctx, spec.expected_structural_deps)
        cap_irr = calculate_irrelevant_code_ratio(cap_ctx, spec.unrelated_symbols)
        cap_red = round((1.0 - (cap_tok / full_tokens)) * 100.0, 2)

        target_dict["capsule_compiler"] = {
            "tokens": cap_tok,
            "reduction_percent": cap_red,
            "latency_ms": round(cap_lat, 2),
            "dependency_recall": round(cap_rec, 2),
            "irrelevant_code_ratio": round(cap_irr, 2),
        }
        total_capsule_tokens += cap_tok

        target_results.append(target_dict)

    # Calculate Aggregate Metrics mathematically from total token sums
    aggregate_reduction_percent = round((1.0 - (total_capsule_tokens / total_full_tokens)) * 100.0, 2)
    mean_compilation_latency = round(sum(capsule_latencies) / len(capsule_latencies), 2)

    # Mean structural recall and irrelevant ratios across targets
    mean_cap_recall = sum(t["capsule_compiler"]["dependency_recall"] for t in target_results) / len(target_results)
    mean_cap_irr = sum(t["capsule_compiler"]["irrelevant_code_ratio"] for t in target_results) / len(target_results)

    benchmark_summary = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "benchmark_repo": "synthetic_multimodule_benchmark_repo",
            "tokenizer": tokenizer.tokenizer_name,
            "total_targets": len(targets),
        },
        "target_benchmarks": target_results,
        "aggregate": {
            "total_full_tokens": total_full_tokens,
            "total_capsule_tokens": total_capsule_tokens,
            "aggregate_reduction_percent": aggregate_reduction_percent,
            "mean_compilation_latency_ms": mean_compilation_latency,
            "mean_capsule_structural_recall": round(mean_cap_recall, 2),
            "mean_capsule_irrelevant_code_ratio": round(mean_cap_irr, 2),
            "vector_sim_totals": vector_totals,
        },
    }

    return benchmark_summary


def print_benchmark_report(summary: Dict[str, Any]) -> None:
    print("\n" + "=" * 90)
    print("CAPSULEMCP ALGORITHMIC CONTEXT COMPILER BENCHMARK REPORT")
    print("=" * 90)

    for tb in summary["target_benchmarks"]:
        print(f"\n[TARGET]: {tb['name']}")
        print(f"Target Unit: {tb['target_unit']} in {tb['target_file']}")
        print("-" * 90)
        print(f"{'Method':<32} | {'Tokens':<8} | {'Reduction':<10} | {'Latency':<9} | {'Recall':<8} | {'Irrelevant':<10}")
        print("-" * 90)

        # Full context
        fc = tb["full_context"]
        print(f"{'Full Context (Naive Repo)':<32} | {fc['tokens']:<8} | {fc['reduction_percent']:>8.2f}% | {fc['latency_ms']:>6.2f}ms | {fc['dependency_recall']*100:>6.1f}% | {fc['irrelevant_code_ratio']*100:>8.1f}%")

        # Vector simulations
        for v_name, vc in tb["vector_retrieval_simulations"].items():
            disp_name = f"Vector-Style Sim ({v_name})"
            print(f"{disp_name:<32} | {vc['tokens']:<8} | {vc['reduction_percent']:>8.2f}% | {vc['latency_ms']:>6.2f}ms | {vc['dependency_recall']*100:>6.1f}% | {vc['irrelevant_code_ratio']*100:>8.1f}%")

        # Capsule compiler
        cc = tb["capsule_compiler"]
        print(f"{'Capsule Compiler (Ours)':<32} | {cc['tokens']:<8} | {cc['reduction_percent']:>8.2f}% | {cc['latency_ms']:>6.2f}ms | {cc['dependency_recall']*100:>6.1f}% | {cc['irrelevant_code_ratio']*100:>8.1f}%")

    print("\n" + "=" * 90)
    print("AGGREGATE BENCHMARK RESULTS (CALCULATED MATHEMATICALLY ACROSS ALL TARGETS)")
    print("=" * 90)
    agg = summary["aggregate"]
    print(f"Total Full Context Tokens:    {agg['total_full_tokens']} tokens")
    print(f"Total Capsule Compiler Tokens: {agg['total_capsule_tokens']} tokens")
    print(f"Aggregate Token Reduction:     {agg['aggregate_reduction_percent']:.2f}% (calculated via 1 - total_capsule / total_full)")
    print(f"Mean Structural Recall:        {agg['mean_capsule_structural_recall']*100:.1f}%")
    print(f"Mean Irrelevant Code Ratio:    {agg['mean_capsule_irrelevant_code_ratio']*100:.1f}%")
    print(f"Mean Compilation Latency:      {agg['mean_compilation_latency_ms']:.2f} ms")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    report = run_benchmark()
    print_benchmark_report(report)
    out_file = Path(__file__).parent / "benchmark_results.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Deterministic benchmark output saved to {out_file}")

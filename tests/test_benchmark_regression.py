"""
Regression tests for CodeAnalyzer interface, benchmark baselines, and context compilation.
Validates metric consistency, mathematical correctness, bounded intervals, and deterministic output.
"""

from pathlib import Path
import pytest

from benchmark.baselines import (
    generate_capsule_context,
    generate_full_context,
    generate_vector_retrieval_simulation,
)
from benchmark.generate_repo import generate_benchmark_repo
from benchmark.run_benchmark import (
    calculate_structural_dependency_recall,
    calculate_irrelevant_code_ratio,
    run_benchmark,
)
from capsulemcp.adapters.interfaces import CodeAnalyzer
from capsulemcp.ast_extractor import ASTExtractor, PythonASTAnalyzer
from capsulemcp.context_compiler import ContextCompiler
from capsulemcp.models import CodeUnit, DependencyUnit


class DummyCustomAnalyzer(CodeAnalyzer):
    """Custom test analyzer validating that ContextCompiler supports swappable analyzers."""

    def parse_file(self, file_path):
        return ("dummy_tree", "def custom_dummy(): pass")

    def extract_imports(self, tree, source):
        return ["import sys"]

    def find_target_unit(self, tree, source, target_name=None, subtask_description=""):
        return CodeUnit(
            name="custom_dummy",
            unit_type="function",
            source_code="def custom_dummy(): pass",
            start_line=1,
            end_line=1,
        )

    def extract_local_dependencies(self, target_file_path, target_unit_node, tree, max_depth=1):
        return [
            DependencyUnit(
                name="dep_dummy",
                file_path="dummy.py",
                unit_type="function",
                source_code="def dep_dummy(): pass",
            )
        ]


def test_code_analyzer_interface_conformance():
    """Verify ASTExtractor satisfies CodeAnalyzer interface and alias exists."""
    assert issubclass(ASTExtractor, CodeAnalyzer)
    assert PythonASTAnalyzer is ASTExtractor

    analyzer = ASTExtractor()
    assert isinstance(analyzer, CodeAnalyzer)


def test_swappable_code_analyzer_in_compiler(tmp_path):
    """Verify compiler works seamlessly with a custom swappable CodeAnalyzer."""
    dummy_file = tmp_path / "foo.py"
    dummy_file.write_text("def test(): pass", encoding="utf-8")

    custom_analyzer = DummyCustomAnalyzer()
    compiler = ContextCompiler(repo_path=str(tmp_path), code_analyzer=custom_analyzer)

    capsule = compiler.generate_context_capsule(
        file_path=str(dummy_file),
        subtask_description="Test custom analyzer",
    )

    assert capsule.target_unit.name == "custom_dummy"
    assert capsule.imports == ["import sys"]
    assert len(capsule.dependencies) == 1
    assert capsule.dependencies[0].name == "dep_dummy"


def test_benchmark_metrics_internal_consistency():
    """
    Verify benchmark output produces mathematically valid, bounded, and internally consistent metrics.
    No arbitrary threshold assertions (>40%), only invariant correctness checks.
    """
    res = run_benchmark(top_k_options=[3, 5])
    assert "target_benchmarks" in res
    assert "aggregate" in res
    assert len(res["target_benchmarks"]) == 3

    for tb in res["target_benchmarks"]:
        # Verify metric bounds: 0.0 <= metric <= 1.0 (or 0.0 <= pct <= 100.0)
        for method_key in ["full_context", "capsule_compiler"]:
            m = tb[method_key]
            assert 0.0 <= m["dependency_recall"] <= 1.0, f"Recall out of bounds in {tb['name']}"
            assert 0.0 <= m["irrelevant_code_ratio"] <= 1.0, f"Irrelevant ratio out of bounds in {tb['name']}"
            assert 0.0 <= m["reduction_percent"] <= 100.0, f"Reduction out of bounds in {tb['name']}"
            assert m["tokens"] > 0, f"Tokens must be positive in {tb['name']}"

        # Verify Capsule achieves 100% structural recall on expected dependencies
        assert tb["capsule_compiler"]["dependency_recall"] == 1.0
        # Verify Capsule achieves 0% irrelevant code ratio
        assert tb["capsule_compiler"]["irrelevant_code_ratio"] == 0.0

    # Aggregate token reduction mathematical invariant check:
    # aggregate_reduction = 1 - total_capsule / total_full
    agg = res["aggregate"]
    expected_red = round((1.0 - (agg["total_capsule_tokens"] / agg["total_full_tokens"])) * 100.0, 2)
    assert agg["aggregate_reduction_percent"] == expected_red
    assert 0.0 <= agg["aggregate_reduction_percent"] <= 100.0


def test_baselines_integrity(tmp_path):
    """Verify all baselines produce non-empty strings and valid outputs."""
    repo = generate_benchmark_repo(tmp_path)
    target_file = "src/billing_engine.py"
    target_unit = "execute_user_charge"
    subtask = "Test charge execution"

    full = generate_full_context(repo)
    assert len(full) > 0
    assert "class S3Client" in full

    vec = generate_vector_retrieval_simulation(repo, query=subtask, top_k=2)
    assert len(vec) > 0

    cap, cap_text = generate_capsule_context(repo, target_file, subtask, target_unit)
    assert len(cap_text) > 0
    assert "execute_user_charge" in cap_text
    # Unrelated services must never leak into capsule
    assert "class S3Client" not in cap_text
    assert "class EmailDispatcher" not in cap_text


def test_benchmark_reproducibility(tmp_path):
    """Verify identical runs produce deterministic token counts and metrics."""
    res1 = run_benchmark(top_k_options=[3])
    res2 = run_benchmark(top_k_options=[3])

    assert res1["aggregate"]["total_full_tokens"] == res2["aggregate"]["total_full_tokens"]
    assert res1["aggregate"]["total_capsule_tokens"] == res2["aggregate"]["total_capsule_tokens"]
    assert res1["aggregate"]["aggregate_reduction_percent"] == res2["aggregate"]["aggregate_reduction_percent"]

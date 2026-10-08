"""
Regression tests for CodeAnalyzer interface, benchmark baselines, and context compilation.
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
    calculate_dependency_recall,
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

    def extract_local_dependencies(self, target_file_path, target_unit_node, tree):
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


def test_benchmark_metrics_regression():
    """Verify automated benchmark runs and achieves expected metrics."""
    res = run_benchmark()
    assert "full_context" in res
    assert "vector_retrieval_simulation" in res
    assert "capsule_compiler" in res

    capsule_metrics = res["capsule_compiler"]
    # Capsule should achieve 100% recall on required 1-hop dependencies
    assert capsule_metrics["dependency_recall"] == 1.0
    # Capsule should achieve 0.0% irrelevant code ratio
    assert capsule_metrics["irrelevant_code_ratio"] == 0.0
    # Token reduction should be positive and substantial
    assert capsule_metrics["reduction_percent"] > 40.0


def test_baselines_integrity(tmp_path):
    """Verify all 3 baselines produce non-empty strings and valid recall/irrelevant ratios."""
    repo = generate_benchmark_repo(tmp_path)
    target_file = "src/billing_engine.py"
    target_unit = "execute_user_charge"
    subtask = "Test charge execution"

    full = generate_full_context(repo)
    assert len(full) > 0
    assert "class S3Client" in full

    vec = generate_vector_retrieval_simulation(repo, query=subtask, top_k_chunks=2)
    assert len(vec) > 0

    cap, cap_text = generate_capsule_context(repo, target_file, subtask, target_unit)
    assert len(cap_text) > 0
    assert "execute_user_charge" in cap_text
    # Unrelated services must never leak into capsule
    assert "class S3Client" not in cap_text
    assert "class EmailDispatcher" not in cap_text

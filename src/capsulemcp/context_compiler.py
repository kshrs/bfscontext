"""
Context Compiler: Algorithmic context compilation for multi-agent AI.
"Context is compiled, not summarized."
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from capsulemcp.adapters.interfaces import CodeAnalyzer, IntentProvider, TelemetrySink
from capsulemcp.adapters.mock.mock_intent import MockIntentProvider
from capsulemcp.adapters.mock.mock_telemetry import MockTelemetrySink
from capsulemcp.ast_extractor import ASTExtractor
from capsulemcp.git_utils import get_git_head_sha
from capsulemcp.models import ContextCapsule, TokenMetrics
from capsulemcp.tokenizer import TokenCounter

logger = logging.getLogger(__name__)


class ContextCompiler:
    """
    Algorithmic Context Compiler.
    Compiles minimal sufficient context capsules for worker agents by extracting
    syntactic units, imports, 1-hop dependencies, git state, and temporal intent.
    """

    def __init__(
        self,
        repo_path: str = ".",
        intent_provider: Optional[IntentProvider] = None,
        telemetry_sink: Optional[TelemetrySink] = None,
        token_counter: Optional[TokenCounter] = None,
        code_analyzer: Optional[CodeAnalyzer] = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.intent_provider = intent_provider or MockIntentProvider()
        self.telemetry_sink = telemetry_sink or MockTelemetrySink()
        self.token_counter = token_counter or TokenCounter()
        self.code_analyzer = code_analyzer or ASTExtractor(repo_path=str(self.repo_path))
        # Keep ast_extractor attribute for backwards compatibility
        self.ast_extractor = self.code_analyzer

    def _collect_raw_repository_context(self, target_file_path: Path) -> str:
        """
        Gathers the uncompiled baseline context (all Python files in the repository or package)
        to measure true token reduction against the complete uncompiled codebase.
        """
        raw_parts = []
        # Look for source files in target_file's parent or src directory
        search_roots = [target_file_path.parent, self.repo_path / "src", self.repo_path]
        seen_files = set()

        for root in search_roots:
            if not root.exists():
                continue
            for py_file in root.rglob("*.py"):
                if py_file.is_file() and py_file not in seen_files:
                    seen_files.add(py_file)
                    try:
                        content = py_file.read_text(encoding="utf-8")
                        rel_path = py_file.relative_to(self.repo_path)
                    except Exception:
                        try:
                            content = py_file.read_text(encoding="latin-1")
                            rel_path = py_file.name
                        except Exception:
                            continue
                    raw_parts.append(f"### File: {rel_path}\n{content}\n")

        return "\n".join(raw_parts)

    def generate_context_capsule(
        self,
        file_path: str,
        subtask_description: str,
        intent_summary: Optional[str] = None,
        target_unit_name: Optional[str] = None,
        repo_path: Optional[str] = None,
    ) -> ContextCapsule:
        """
        Compiles the minimal sufficient ContextCapsule.

        Args:
            file_path: Path to the target file (relative to repo_path or absolute).
            subtask_description: The delegated task prompt or instruction.
            intent_summary: Optional intent hint to provide to the IntentProvider.
            target_unit_name: Optional explicit name of the function or class.
            repo_path: Optional override for the repository path.

        Returns:
            A deterministic ContextCapsule object with rendered text and token metrics.
        """
        active_repo = Path(repo_path).resolve() if repo_path else self.repo_path
        target_path = Path(file_path)
        if not target_path.is_absolute():
            target_path = (active_repo / target_path).resolve()

        # 1. Track A: State - Parse AST & extract complete syntactic unit
        tree, source = self.ast_extractor.parse_file(target_path)
        imports = self.ast_extractor.extract_imports(tree, source)
        target_unit = self.ast_extractor.find_target_unit(
            tree, source, target_name=target_unit_name, subtask_description=subtask_description
        )

        # Controlled 1-hop dependency expansion
        # Find local AST node for target unit
        target_node = None
        tree_body = getattr(tree, "body", None)
        if isinstance(tree_body, list):
            for node in tree_body:
                if getattr(node, "name", None) == target_unit.name:
                    target_node = node
                    break
        else:
            target_node = tree

        dependencies = []
        if target_node is not None:
            dependencies = self.code_analyzer.extract_local_dependencies(target_path, target_node, tree)

        # Git HEAD SHA
        git_head_sha = get_git_head_sha(str(active_repo))

        # 2. Track B: Intent - Retrieve intent & check temporal Git alignment
        rel_file_str = str(target_path.relative_to(active_repo)) if active_repo in target_path.parents else target_path.name
        intent_ctx = self.intent_provider.get_relevant_intent(
            subtask_description=subtask_description,
            file_path=rel_file_str,
            current_head_sha=git_head_sha,
            intent_hint=intent_summary,
        )

        # 3. Construct Context Capsule
        capsule = ContextCapsule(
            task_instructions=subtask_description,
            intent_context=intent_ctx,
            target_unit=target_unit,
            imports=imports,
            dependencies=dependencies,
            git_head_sha=git_head_sha,
            target_file_path=rel_file_str,
        )

        # 4. Token Metrics Calculation
        rendered_capsule = capsule.render()
        raw_context = self._collect_raw_repository_context(target_path)
        raw_tokens, cap_tokens, saved, reduction_pct, tok_name = self.token_counter.calculate_metrics(
            raw_context, rendered_capsule
        )

        metrics = TokenMetrics(
            raw_context_tokens=raw_tokens,
            capsule_tokens=cap_tokens,
            tokens_saved=saved,
            reduction_percent=reduction_pct,
            tokenizer_name=tok_name,
        )
        capsule.token_metrics = metrics

        # 5. Record Telemetry
        if self.telemetry_sink:
            self.telemetry_sink.record_compilation(capsule, metrics)

        return capsule


def generate_context_capsule(
    file_path: str,
    subtask_description: str,
    intent_summary: Optional[str] = None,
    repo_path: str = ".",
    target_unit_name: Optional[str] = None,
) -> ContextCapsule:
    """Convenience functional API for context capsule generation."""
    compiler = ContextCompiler(repo_path=repo_path)
    return compiler.generate_context_capsule(
        file_path=file_path,
        subtask_description=subtask_description,
        intent_summary=intent_summary,
        target_unit_name=target_unit_name,
    )

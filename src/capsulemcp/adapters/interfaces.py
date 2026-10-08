"""
Abstract interfaces for pluggable team-owned components and code analyzers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from capsulemcp.models import CodeUnit, ContextCapsule, DependencyUnit, IntentContext, TokenMetrics


class CodeAnalyzer(ABC):
    """
    Interface for Track A syntax and structure extraction.
    Allows swappable implementations (e.g. Python AST, Tree-sitter, language servers).
    """

    @abstractmethod
    def parse_file(self, file_path: str | Path) -> Tuple[Any, str]:
        """Read and parse a source file into a parse tree/AST and raw code string."""
        pass

    @abstractmethod
    def extract_imports(self, tree: Any, source: str) -> List[str]:
        """Extract all import statements preserving source contracts."""
        pass

    @abstractmethod
    def find_target_unit(
        self,
        tree: Any,
        source: str,
        target_name: Optional[str] = None,
        subtask_description: str = "",
    ) -> CodeUnit:
        """Locate complete syntactic unit (function or class) in parsed tree."""
        pass

    @abstractmethod
    def extract_local_dependencies(
        self,
        target_file_path: str | Path,
        target_unit_node: Any,
        tree: Any,
    ) -> List[DependencyUnit]:
        """Controlled 1-hop local dependency expansion."""
        pass


class IntentProvider(ABC):
    """Interface for Track B semantic intent retrieval."""

    @abstractmethod
    def get_relevant_intent(
        self,
        subtask_description: str,
        file_path: str,
        current_head_sha: str,
        intent_hint: Optional[str] = None,
    ) -> IntentContext:
        """Retrieve relevant intent context aligned with repository Git state."""
        pass


class WorkerProvider(ABC):
    """Interface for delegating context capsules to worker models/agents."""

    @abstractmethod
    def generate(self, capsule: ContextCapsule) -> Dict[str, Any]:
        """Dispatch compiled context capsule to worker and return generated artifact/result."""
        pass


class TelemetrySink(ABC):
    """Interface for recording context compilation and token metrics."""

    @abstractmethod
    def record_compilation(
        self,
        capsule: ContextCapsule,
        metrics: TokenMetrics,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record compilation event, token reduction, and runtime metadata."""
        pass

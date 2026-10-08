"""
Abstract interfaces for pluggable team-owned components.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from capsulemcp.models import ContextCapsule, IntentContext, TokenMetrics


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

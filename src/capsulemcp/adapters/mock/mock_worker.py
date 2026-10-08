"""
Mock implementation of WorkerProvider for testing worker delegation.
Clearly isolated and designated as MOCK / DEMO ONLY.
"""

from __future__ import annotations

from typing import Any, Dict

from capsulemcp.adapters.interfaces import WorkerProvider
from capsulemcp.models import ContextCapsule


class MockWorkerProvider(WorkerProvider):
    """
    Simulates a worker LLM generating artifacts based on a compiled Context Capsule.
    MOCK / DEMO ONLY: This is not actual LLM output.
    """

    def generate(self, capsule: ContextCapsule) -> Dict[str, Any]:
        """Generate deterministic sample response."""
        return {
            "status": "success",
            "is_mock": True,
            "disclaimer": "MOCK / DEMO ONLY - Simulated worker response",
            "target_unit": capsule.target_unit.name,
            "target_file": capsule.target_file_path,
            "git_head_sha": capsule.git_head_sha,
            "generated_code": (
                f"# Generated test stub for {capsule.target_unit.name}\n"
                f"import pytest\n"
                f"# Contracts verified from capsule: imports={len(capsule.imports)}, "
                f"dependencies={len(capsule.dependencies)}\n\n"
                f"def test_{capsule.target_unit.name}_execution():\n"
                f"    # Mock test generated from contract\n"
                f"    pass\n"
            ),
        }

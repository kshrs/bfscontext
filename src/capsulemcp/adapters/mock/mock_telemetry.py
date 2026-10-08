"""
Mock implementation of TelemetrySink for testing and logging context metrics.
Clearly isolated and designated as MOCK / DEMO ONLY.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from capsulemcp.adapters.interfaces import TelemetrySink
from capsulemcp.models import ContextCapsule, TokenMetrics

logger = logging.getLogger(__name__)


class MockTelemetrySink(TelemetrySink):
    """
    In-memory telemetry sink recording real token measurements for verification.
    MOCK / DEMO ONLY: Stores events in an in-memory list instead of external service.
    """

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []

    def record_compilation(
        self,
        capsule: ContextCapsule,
        metrics: TokenMetrics,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store recorded event."""
        record = {
            "target_unit": capsule.target_unit.name,
            "target_file": capsule.target_file_path,
            "git_head_sha": capsule.git_head_sha,
            "metrics": metrics.to_dict(),
            "metadata": metadata or {},
        }
        self.records.append(record)
        logger.info(
            "Telemetry recorded: unit=%s, tokens_saved=%d (%.2f%%)",
            capsule.target_unit.name,
            metrics.tokens_saved,
            metrics.reduction_percent,
        )

    def clear(self) -> None:
        self.records.clear()

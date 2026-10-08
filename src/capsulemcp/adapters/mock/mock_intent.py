"""
Mock implementation of IntentProvider for development and integration testing.
Clearly isolated and designated as MOCK / DEMO ONLY.
"""

from __future__ import annotations

import logging
from typing import Optional

from capsulemcp.adapters.interfaces import IntentProvider
from capsulemcp.git_utils import is_sha_stale
from capsulemcp.models import IntentContext

logger = logging.getLogger(__name__)


class MockIntentProvider(IntentProvider):
    """
    Deterministic mock intent provider.
    MOCK / DEMO ONLY: Does not connect to a production vector database.
    """

    def __init__(
        self,
        default_intent: str = "Migrate authentication flow to token-based validation",
        simulated_commit_sha: Optional[str] = None,
    ) -> None:
        self.default_intent = default_intent
        self.simulated_commit_sha = simulated_commit_sha

    def get_relevant_intent(
        self,
        subtask_description: str,
        file_path: str,
        current_head_sha: str,
        intent_hint: Optional[str] = None,
    ) -> IntentContext:
        """
        Returns deterministic intent context and flags temporal staleness against current Git HEAD.
        """
        intent_text = intent_hint or self.default_intent
        commit_sha = self.simulated_commit_sha or current_head_sha

        is_stale = is_sha_stale(current_head_sha, commit_sha)
        warning = None
        if is_stale:
            warning = f"Intent was created at commit {commit_sha[:8]}, which differs from current HEAD {current_head_sha[:8]}."

        return IntentContext(
            intent=intent_text,
            source="MOCK_INTENT (MOCK / DEMO ONLY)",
            commit_sha=commit_sha,
            is_stale=is_stale,
            warning=warning,
        )

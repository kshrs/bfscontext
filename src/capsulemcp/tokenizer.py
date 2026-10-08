"""
Deterministic tokenizer with tiktoken integration and transparent fallback.
"""

from __future__ import annotations

import logging
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False


class TokenCounter:
    """Calculates token counts using tiktoken (cl100k_base) or fallback estimator."""

    def __init__(self, model_encoding: str = "cl100k_base") -> None:
        self.encoding_name = model_encoding
        self._encoder = None
        if _TIKTOKEN_AVAILABLE:
            try:
                self._encoder = tiktoken.get_encoding(model_encoding)
            except Exception as e:
                logger.warning("Could not initialize tiktoken encoding %s: %s", model_encoding, e)

    @property
    def is_real_tokenizer(self) -> bool:
        return self._encoder is not None

    @property
    def tokenizer_name(self) -> str:
        if self._encoder is not None:
            return f"tiktoken:{self.encoding_name}"
        return "fallback_character_estimator_4chars_per_token"

    def count_tokens(self, text: str) -> int:
        """Count tokens in text deterministically."""
        if not text:
            return 0
        if self._encoder is not None:
            return len(self._encoder.encode(text, disallowed_special=()))
        # Fallback estimator: standard heuristic ~4 characters per token (ceil)
        return max(1, (len(text) + 3) // 4)

    def calculate_metrics(self, raw_text: str, capsule_text: str) -> Tuple[int, int, int, float, str]:
        """
        Calculate token reduction metrics between raw context and compiled capsule.
        Returns:
            (raw_tokens, capsule_tokens, tokens_saved, reduction_percent, tokenizer_name)
        """
        raw_tokens = self.count_tokens(raw_text)
        capsule_tokens = self.count_tokens(capsule_text)
        tokens_saved = max(0, raw_tokens - capsule_tokens)
        reduction_percent = 0.0
        if raw_tokens > 0:
            reduction_percent = (tokens_saved / raw_tokens) * 100.0
        return raw_tokens, capsule_tokens, tokens_saved, reduction_percent, self.tokenizer_name

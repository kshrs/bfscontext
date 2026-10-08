"""
Real LLM Worker Provider: Dispatches compiled Context Capsules to real LLM APIs.
Supports OpenAI / OpenRouter / compatible chat completion endpoints.
Capsule-only: sends ONLY the compiled capsule and instructions, NEVER raw context or repository.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional
import urllib.error
import urllib.request

from capsulemcp.adapters.interfaces import WorkerProvider
from capsulemcp.models import ContextCapsule

logger = logging.getLogger(__name__)


class RealWorkerProvider(WorkerProvider):
    """
    Real LLM Worker Provider implementing standard OpenAI-compatible Chat Completions API.
    Configured via environment variables:
        CAPSULEMCP_API_KEY: Provider API key
        CAPSULEMCP_MODEL: Model identifier (e.g. 'gpt-4o', 'deepseek-chat', 'claude-3-5-sonnet')
        CAPSULEMCP_BASE_URL: Optional endpoint URL (default: 'https://api.openai.com/v1')
    """

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 30.0,
        http_client: Optional[Any] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("CAPSULEMCP_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("CAPSULEMCP_MODEL") or os.getenv("DEFAULT_WORKER_MODEL", self.DEFAULT_MODEL)
        self.base_url = (base_url or os.getenv("CAPSULEMCP_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._http_client = http_client  # Injectable for unit tests

        # Track the exact payload sent in the last request for inspection/testing
        self.last_sent_payload: Optional[Dict[str, Any]] = None

    @property
    def is_configured(self) -> bool:
        """Returns True if an API key is present."""
        return bool(self.api_key and self.api_key.strip())

    def generate(self, capsule: ContextCapsule) -> Dict[str, Any]:
        """
        Dispatches compiled ContextCapsule to the real LLM endpoint.
        Sends ONLY the capsule prompt, never the entire repository or raw context.
        """
        t0 = time.perf_counter()

        if not self.is_configured:
            return {
                "status": "error",
                "is_mock": False,
                "model": self.model,
                "error": "Missing API key: CAPSULEMCP_API_KEY environment variable is not set.",
                "generated_code": "",
                "latency_ms": 0.0,
            }

        # Build capsule-only prompt
        rendered_capsule = capsule.render()
        system_instruction = (
            "You are an expert AI code generator. You must implement or test the requested target unit.\n"
            "Adhere strictly to the immutable code contracts, imports, types, and dependencies specified in the capsule.\n"
            "Return ONLY the clean Python code block. Do not include markdown conversational filler."
        )

        user_content = (
            f"Here is the compiled Context Capsule for the delegated subtask:\n\n"
            f"{rendered_capsule}\n\n"
            f"Please generate the implementation or tests for `{capsule.target_unit.name}`."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
        }
        self.last_sent_payload = payload

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            url = f"{self.base_url}/chat/completions"

            if self._http_client is not None:
                # Use injected test client
                resp_dict = self._http_client(url, headers, req_data)
            else:
                req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    raw_body = response.read().decode("utf-8")
                    resp_dict = json.loads(raw_body)

            latency_ms = (time.perf_counter() - t0) * 1000.0

            # Parse choices
            choices = resp_dict.get("choices", [])
            if not choices:
                return {
                    "status": "error",
                    "is_mock": False,
                    "model": self.model,
                    "error": "Empty choices in API response",
                    "generated_code": "",
                    "latency_ms": round(latency_ms, 2),
                }

            generated_code = choices[0].get("message", {}).get("content", "").strip()

            return {
                "status": "success",
                "is_mock": False,
                "model": self.model,
                "generated_code": generated_code,
                "latency_ms": round(latency_ms, 2),
                "target_unit": capsule.target_unit.name,
                "target_file": capsule.target_file_path,
                "git_head_sha": capsule.git_head_sha,
                "usage": resp_dict.get("usage", {}),
            }

        except urllib.error.HTTPError as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            error_body = e.read().decode("utf-8") if e.fp else str(e)
            logger.warning("HTTP error calling real worker API (%s): %s", e.code, error_body)
            return {
                "status": "error",
                "is_mock": False,
                "model": self.model,
                "error": f"HTTP {e.code}: {error_body}",
                "generated_code": "",
                "latency_ms": round(latency_ms, 2),
            }
        except urllib.error.URLError as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("Network URL error calling real worker API: %s", e.reason)
            return {
                "status": "error",
                "is_mock": False,
                "model": self.model,
                "error": f"Network error: {e.reason}",
                "generated_code": "",
                "latency_ms": round(latency_ms, 2),
            }
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("Unexpected error calling real worker API: %s", e)
            return {
                "status": "error",
                "is_mock": False,
                "model": self.model,
                "error": str(e),
                "generated_code": "",
                "latency_ms": round(latency_ms, 2),
            }

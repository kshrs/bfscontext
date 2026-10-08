"""
Unit tests for capsule_mcp MCP gateway tool.
Provides dynamic isolation harness mocking external teammate modules:
- capsule_engine
- circuit_breaker
- telemetry
- litellm
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch
import pytest

# ---------------------------------------------------------------------------
# Dynamic Isolation Harness: Mock teammate modules before importing capsule_mcp
# ---------------------------------------------------------------------------

# 1. Mock capsule_engine
mock_capsule_engine = types.ModuleType("capsule_engine")
mock_generate_context_capsule = MagicMock()
mock_capsule_engine.generate_context_capsule = mock_generate_context_capsule
sys.modules["capsule_engine"] = mock_capsule_engine

# 2. Mock circuit_breaker
mock_circuit_breaker = types.ModuleType("circuit_breaker")
mock_validate_and_safeguard = MagicMock()
mock_circuit_breaker.validate_and_safeguard = mock_validate_and_safeguard
sys.modules["circuit_breaker"] = mock_circuit_breaker

# 3. Mock telemetry
mock_telemetry = types.ModuleType("telemetry")
mock_log_delegation_metrics = MagicMock()
mock_telemetry.log_delegation_metrics = mock_log_delegation_metrics
sys.modules["telemetry"] = mock_telemetry

# Import the module under test (will fail in Red stage until capsule_mcp.py is created)
try:
    import capsule_mcp
except ImportError:
    capsule_mcp = None


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all dynamic module mocks before each test."""
    mock_generate_context_capsule.reset_mock()
    mock_validate_and_safeguard.reset_mock()
    mock_log_delegation_metrics.reset_mock()


def test_capsule_mcp_module_exists():
    """Verify that capsule_mcp module is importable."""
    assert capsule_mcp is not None, "capsule_mcp module could not be imported"


def test_delegate_with_capsule_success(tmp_path):
    """
    Test 1: Valid code generation.
    Ensures directory is created, file is written to disk, telemetry is logged,
    and success payload is returned.
    """
    target_file = str(tmp_path / "src" / "new_feature.py")
    subtask = "Implement hello world function"
    intent = "Add greeting utility"

    # Mock capsule engine output
    mock_generate_context_capsule.return_value = {
        "capsule_prompt": "[TASK INSTRUCTIONS]\nImplement hello world",
        "commit_sha": "7f4a9b2c",
        "raw_file_tokens": 1200,
        "capsule_tokens": 60,
        "tokens_saved": 1140,
        "compression_ratio": 0.95,
    }

    # Mock LLM response
    fake_llm_response = MagicMock()
    fake_llm_response.choices = [
        MagicMock(message=MagicMock(content="```python\ndef hello():\n    return 'world'\n```"))
    ]

    # Mock circuit breaker output for SUCCESS
    mock_validate_and_safeguard.return_value = {
        "status": "SUCCESS",
        "clean_code": "def hello():\n    return 'world'\n",
        "syntax_valid": True,
        "auto_fix_attempted": False,
        "rolled_back": False,
        "error_message": None,
        "target_file_path": target_file,
    }

    with patch("capsule_mcp.litellm.completion", return_value=fake_llm_response) as mock_litellm:
        result = capsule_mcp.delegate_with_capsule(
            target_file=target_file,
            subtask=subtask,
            intent=intent,
            worker_model="openrouter/deepseek/deepseek-coder",
        )

        # Assert capsule engine was called with expected arguments
        mock_generate_context_capsule.assert_called_once_with(
            file_path=target_file,
            subtask_description=subtask,
            intent_summary=intent,
            repo_path=".",
        )

        # Assert LiteLLM completion dispatched capsule prompt
        mock_litellm.assert_called_once()
        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs["model"] == "openrouter/deepseek/deepseek-coder"
        assert "[TASK INSTRUCTIONS]" in call_kwargs["messages"][0]["content"]

        # Assert circuit breaker was invoked with fixer callable
        mock_validate_and_safeguard.assert_called_once()
        cb_kwargs = mock_validate_and_safeguard.call_args[1]
        assert cb_kwargs["target_file_path"] == target_file
        assert callable(cb_kwargs.get("fixer_llm_callable"))

        # Assert file was written to disk
        assert os.path.exists(target_file)
        with open(target_file, "r", encoding="utf-8") as f:
            assert f.read() == "def hello():\n    return 'world'\n"

        # Assert telemetry was logged
        mock_log_delegation_metrics.assert_called_once()

        # Assert result structure
        assert result["status"] == "success"
        assert result["artifact_written"] == target_file
        assert result["tokens_saved"] == 1140
        assert result["guardrail_status"] == "PASSED"


def test_delegate_with_capsule_circuit_breaker_tripped(tmp_path):
    """
    Test 2: Circuit breaker trips due to persistent syntax failure.
    Ensures no file is written to disk, status is 'failed', and error details
    are returned cleanly without crashing.
    """
    target_file = str(tmp_path / "src" / "broken_file.py")
    subtask = "Implement broken function"
    intent = "Test failure injection"

    # Mock capsule engine output
    mock_generate_context_capsule.return_value = {
        "capsule_prompt": "Broken task prompt",
        "commit_sha": "abc1234",
        "raw_file_tokens": 800,
        "capsule_tokens": 100,
        "tokens_saved": 700,
        "compression_ratio": 0.875,
    }

    fake_llm_response = MagicMock()
    fake_llm_response.choices = [
        MagicMock(message=MagicMock(content="def bad_syntax(: pass"))
    ]

    # Mock circuit breaker output for CIRCUIT_BREAKER_TRIPPED
    mock_validate_and_safeguard.return_value = {
        "status": "CIRCUIT_BREAKER_TRIPPED",
        "clean_code": "",
        "syntax_valid": False,
        "auto_fix_attempted": True,
        "rolled_back": True,
        "error_message": "SyntaxError: invalid syntax",
        "target_file_path": target_file,
    }

    with patch("capsule_mcp.litellm.completion", return_value=fake_llm_response):
        result = capsule_mcp.delegate_with_capsule(
            target_file=target_file,
            subtask=subtask,
            intent=intent,
        )

        # Assert no file was written to disk
        assert not os.path.exists(target_file)

        # Assert telemetry still logged the failed event
        mock_log_delegation_metrics.assert_called_once()

        # Assert structured failure payload
        assert result["status"] == "failed"
        assert result["guardrail_status"] == "CIRCUIT_BREAKER_TRIPPED"
        assert "SyntaxError: invalid syntax" in result["error"]
        assert result.get("artifact_written") is None


def test_fixer_llm_callable_delegation():
    """
    Test 3: Verify fixer_llm_callable helper correctly prompts LiteLLM with broken code and error.
    """
    broken_code = "def foo(\n    return 42"
    error_msg = "SyntaxError: '(' was never closed"

    repaired_code_markdown = "```python\ndef foo():\n    return 42\n```"
    fake_repair_response = MagicMock()
    fake_repair_response.choices = [
        MagicMock(message=MagicMock(content=repaired_code_markdown))
    ]

    with patch("capsule_mcp.litellm.completion", return_value=fake_repair_response) as mock_repair_llm:
        fixed_output = capsule_mcp.fixer_llm_callable(broken_code, error_msg)

        mock_repair_llm.assert_called_once()
        repair_messages = mock_repair_llm.call_args[1]["messages"]
        user_content = repair_messages[0]["content"]

        assert broken_code in user_content
        assert error_msg in user_content
        assert fixed_output == repaired_code_markdown

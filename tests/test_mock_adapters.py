"""
Tests for mock adapters (Intent, Worker, Telemetry).
"""

from capsulemcp.adapters.mock import MockIntentProvider, MockTelemetrySink, MockWorkerProvider
from capsulemcp.models import CodeUnit, ContextCapsule, IntentContext, TokenMetrics


def test_mock_intent_provider_fresh():
    provider = MockIntentProvider(default_intent="Test Intent")
    res = provider.get_relevant_intent("do task", "src/foo.py", current_head_sha="sha123")
    assert res.intent == "Test Intent"
    assert res.is_stale is False
    assert "MOCK / DEMO ONLY" in res.source
    assert res.warning is None


def test_mock_intent_provider_stale():
    provider = MockIntentProvider(default_intent="Stale Intent", simulated_commit_sha="old_sha")
    res = provider.get_relevant_intent("do task", "src/foo.py", current_head_sha="new_sha")
    assert res.is_stale is True
    assert res.warning is not None
    assert "old_sha" in res.warning
    formatted = res.format_block()
    assert "[HISTORICAL: MAY BE DEPRECATED]" in formatted
    assert "MOCK / DEMO ONLY" in formatted


def test_mock_worker_provider():
    worker = MockWorkerProvider()
    capsule = ContextCapsule(
        task_instructions="write tests",
        intent_context=IntentContext("intent", "MOCK", "sha"),
        target_unit=CodeUnit("my_fn", "function", "def my_fn(): pass", 1, 1),
        imports=[],
        dependencies=[],
        git_head_sha="sha",
        target_file_path="src/foo.py",
    )
    result = worker.generate(capsule)
    assert result["status"] == "success"
    assert result["is_mock"] is True
    assert "my_fn" in result["generated_code"]


def test_mock_telemetry_sink():
    sink = MockTelemetrySink()
    capsule = ContextCapsule(
        task_instructions="write tests",
        intent_context=IntentContext("intent", "MOCK", "sha"),
        target_unit=CodeUnit("my_fn", "function", "def my_fn(): pass", 1, 1),
        imports=[],
        dependencies=[],
        git_head_sha="sha",
        target_file_path="src/foo.py",
    )
    metrics = TokenMetrics(100, 30, 70, 70.0, "tiktoken")
    sink.record_compilation(capsule, metrics)
    assert len(sink.records) == 1
    assert sink.records[0]["target_unit"] == "my_fn"
    assert sink.records[0]["metrics"]["tokens_saved"] == 70

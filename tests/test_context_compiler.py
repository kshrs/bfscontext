"""
Tests for ContextCompiler end-to-end functionality.
"""

from pathlib import Path
import pytest
from capsulemcp.adapters.mock import MockIntentProvider, MockTelemetrySink
from capsulemcp.context_compiler import ContextCompiler, generate_context_capsule


@pytest.fixture
def demo_repo_path():
    return Path(__file__).parent.parent / "demo" / "sample_repo"


def test_capsule_construction_and_sections(demo_repo_path):
    compiler = ContextCompiler(repo_path=str(demo_repo_path))
    target_file = demo_repo_path / "src" / "billing.py"

    capsule = compiler.generate_context_capsule(
        file_path=str(target_file),
        subtask_description="Test charge_user",
        target_unit_name="charge_user",
    )

    rendered = capsule.render()

    assert "[TASK INSTRUCTIONS]" in rendered
    assert "[INTENT CONTEXT]" in rendered
    assert "[IMMUTABLE CODE CONTRACTS]" in rendered
    assert "[DEPENDENCIES]" in rendered
    assert "[TARGET ARTIFACT CONTRACT]" in rendered

    # Target unit should be present
    assert "def charge_user(" in rendered
    # Irrelevant function should not be in target contract
    assert "def handle_stripe_webhook(" not in capsule.target_unit.source_code


def test_token_calculation_and_real_metrics(demo_repo_path):
    telemetry = MockTelemetrySink()
    compiler = ContextCompiler(repo_path=str(demo_repo_path), telemetry_sink=telemetry)
    target_file = demo_repo_path / "src" / "billing.py"

    capsule = compiler.generate_context_capsule(
        file_path=str(target_file),
        subtask_description="Test charge_user",
        target_unit_name="charge_user",
    )

    assert capsule.token_metrics is not None
    m = capsule.token_metrics
    assert m.raw_context_tokens > 0
    assert m.capsule_tokens > 0
    assert m.tokens_saved == m.raw_context_tokens - m.capsule_tokens
    assert 0.0 <= m.reduction_percent <= 100.0
    assert len(telemetry.records) == 1


def test_deterministic_repeated_execution(demo_repo_path):
    compiler = ContextCompiler(repo_path=str(demo_repo_path))
    target_file = demo_repo_path / "src" / "billing.py"

    cap1 = compiler.generate_context_capsule(
        file_path=str(target_file),
        subtask_description="Test charge_user",
        target_unit_name="charge_user",
    )
    cap2 = compiler.generate_context_capsule(
        file_path=str(target_file),
        subtask_description="Test charge_user",
        target_unit_name="charge_user",
    )

    assert cap1.render() == cap2.render()
    assert cap1.token_metrics.capsule_tokens == cap2.token_metrics.capsule_tokens


def test_historical_intent_detection(demo_repo_path):
    stale_intent_provider = MockIntentProvider(
        default_intent="Outdated schema migration",
        simulated_commit_sha="1111111111111111111111111111111111111111",
    )
    compiler = ContextCompiler(
        repo_path=str(demo_repo_path),
        intent_provider=stale_intent_provider,
    )
    target_file = demo_repo_path / "src" / "billing.py"

    capsule = compiler.generate_context_capsule(
        file_path=str(target_file),
        subtask_description="Test charge_user",
        target_unit_name="charge_user",
    )

    rendered = capsule.render()
    assert "[HISTORICAL: MAY BE DEPRECATED]" in rendered
    assert capsule.intent_context.is_stale is True


def test_convenience_api(demo_repo_path):
    target_file = demo_repo_path / "src" / "billing.py"
    capsule = generate_context_capsule(
        file_path=str(target_file),
        subtask_description="Test charge_user",
        repo_path=str(demo_repo_path),
        target_unit_name="charge_user",
    )
    assert capsule.target_unit.name == "charge_user"

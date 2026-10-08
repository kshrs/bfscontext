"""
Tests for telemetry module and Rich terminal dashboard.
Verifies:
1. Exact API signature of log_delegation_metrics
2. Mathematical safety of token calculations (no division by zero)
3. Rich rendering of NAIVE vs COMPILED context
4. Status badge formatting
"""

from io import StringIO
import pytest
from rich.console import Console

from capsulemcp.telemetry import (
    calculate_token_savings,
    format_status_badge,
    log_delegation_metrics,
    log_granular_stage_latencies,
)


def test_calculate_token_savings_normal():
    saved, pct = calculate_token_savings(1000, 400)
    assert saved == 600
    assert pytest.approx(pct, 0.01) == 60.0


def test_calculate_token_savings_zero_raw():
    saved, pct = calculate_token_savings(0, 0)
    assert saved == 0
    assert pct == 0.0


def test_calculate_token_savings_negative_diff():
    # If capsule happens to be larger, saved is floored at 0
    saved, pct = calculate_token_savings(100, 150)
    assert saved == 0
    assert pct == 0.0


def test_format_status_badge():
    assert "SUCCESS" in str(format_status_badge("SUCCESS"))
    assert "REPAIRED" in str(format_status_badge("REPAIRED"))
    assert "CIRCUIT_BREAKER_TRIPPED" in str(format_status_badge("CIRCUIT_BREAKER_TRIPPED"))


def test_log_delegation_metrics_output():
    buf = StringIO()
    test_console = Console(file=buf, force_terminal=True, width=100)

    log_delegation_metrics(
        raw_tokens=712,
        capsule_tokens=648,
        latency_sec=0.042,
        status="SUCCESS",
        artifact="billing.charge_user",
        console=test_console,
    )

    output = buf.getvalue()
    assert "712" in output
    assert "648" in output
    assert "64" in output
    assert "8.99%" in output
    assert "billing.charge_user" in output
    assert "SUCCESS" in output


def test_log_granular_stage_latencies_output():
    buf = StringIO()
    test_console = Console(file=buf, force_terminal=True, width=100)

    log_granular_stage_latencies(
        compiler_ms=12.5,
        worker_ms=150.0,
        guardrail_ms=2.1,
        total_ms=164.6,
        request_id="req-test-99",
        console=test_console,
    )

    output = buf.getvalue()
    assert "req-test-99" in output
    assert "12.50 ms" in output
    assert "150.00 ms" in output
    assert "2.10 ms" in output

"""
Demonstration runner for CapsuleMCP:
Combines Context Compilation, Worker Delegation, One-Strike Guardrail,
and Rich Terminal Telemetry Dashboard.

Usage:
    python demo/run_demo.py
    python demo/run_demo.py --simulate-error
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

# Ensure repository root and src are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from rich.console import Console
from rich.panel import Panel

from capsulemcp.adapters.mock import MockIntentProvider, MockTelemetrySink, MockWorkerProvider
from capsulemcp.circuit_breaker import CircuitBreaker, GuardrailStatus, MockFixerProvider
from capsulemcp.context_compiler import ContextCompiler
from capsulemcp.git_utils import get_git_head_sha
from capsulemcp.telemetry import log_delegation_metrics, log_granular_stage_latencies
from demo.run_failure_demo import run_failure_scenarios


def main() -> None:
    parser = argparse.ArgumentParser(description="CapsuleMCP Live Demonstration")
    parser.add_argument(
        "--simulate-error",
        action="store_true",
        help="Run failure injection scenario (worker error -> 1 fix -> circuit breaker)",
    )
    args = parser.parse_args()

    if args.simulate_error:
        run_failure_scenarios(simulate_error=True)
        return

    console = Console()
    repo_path = Path(__file__).parent / "sample_repo"
    target_rel_path = "src/billing.py"
    target_file = repo_path / target_rel_path
    target_symbol = "charge_user"
    subtask = "Write pytest tests for charge_user() verifying balance updates and PaymentError handling."

    console.print("\n" + "=" * 80, style="bold cyan")
    console.print("  CAPSULEMCP LIVE DEMONSTRATION", style="bold yellow")
    console.print("  'Context is compiled, not summarized.'", style="italic white")
    console.print("=" * 80 + "\n", style="bold cyan")

    # 1. Incoming Delegation
    console.print(Panel(
        f"[bold white]Target:[/bold white] {target_rel_path}:{target_symbol}\n"
        f"[bold white]Task:[/bold white] {subtask}\n"
        f"[bold white]Repository:[/bold white] {repo_path}\n"
        f"[bold white]Git HEAD:[/bold white] {get_git_head_sha(str(repo_path))[:8]}",
        title="[bold green]1. Incoming Subtask Delegation[/bold green]",
        border_style="green",
    ))

    # 2. Track B: Intent Context
    intent_provider = MockIntentProvider(
        default_intent="Stripe webhook billing integration with signature validation"
    )
    worker = MockWorkerProvider()
    telemetry = MockTelemetrySink()

    # 3. Context Compiler (Track A: AST + Dependencies)
    compiler = ContextCompiler(
        repo_path=str(repo_path),
        intent_provider=intent_provider,
        telemetry_sink=telemetry,
    )

    t_start = time.perf_counter()
    t_comp_0 = time.perf_counter()
    capsule = compiler.generate_context_capsule(
        file_path=str(target_file),
        subtask_description=subtask,
        target_unit_name=target_symbol,
    )
    comp_latency_ms = (time.perf_counter() - t_comp_0) * 1000.0

    # 4. Context Capsule Generated
    console.print(f"[bold cyan]2. Context Capsule Algorithmically Compiled[/bold cyan]")
    console.print(f"   * Syntactic unit isolated: [green]{capsule.target_unit.name}[/green] ({capsule.target_unit.unit_type})")
    console.print(f"   * Verbatim imports preserved: [green]{len(capsule.imports)}[/green] statements")
    console.print(f"   * 1-Hop Structural Dependencies: [green]{len(capsule.dependencies)}[/green] units")
    for dep in capsule.dependencies:
        console.print(f"       +-- {dep.unit_type} [yellow]{dep.name}[/yellow] (from {dep.file_path})")

    # 5. Worker receives ONLY the capsule
    t_worker_0 = time.perf_counter()
    worker_output = worker.generate(capsule)
    worker_latency_ms = (time.perf_counter() - t_worker_0) * 1000.0

    console.print(f"\n[bold cyan]3. Worker Provider Execution[/bold cyan]")
    console.print(f"   * Worker input: [green]Context Capsule ONLY[/green] (Zero unrelated files)")
    console.print(f"   * Status: [green]{worker_output['status']}[/green]")
    console.print(f"   * Mode: [dim]{worker_output['disclaimer']}[/dim]")

    # 6. Guardrail Evaluation
    guardrail = CircuitBreaker(repo_path=str(repo_path))
    t_guard_0 = time.perf_counter()
    guard_res = guardrail.evaluate_and_guard(
        worker_code=worker_output["generated_code"],
        target_file=str(target_file),
        target_symbol=target_symbol,
    )
    guard_latency_ms = (time.perf_counter() - t_guard_0) * 1000.0
    total_latency_sec = time.perf_counter() - t_start
    total_latency_ms = total_latency_sec * 1000.0

    console.print(f"\n[bold cyan]4. One-Strike Guardrail Evaluation[/bold cyan]")
    console.print(f"   * Status: [bold green]{guard_res.status.value}[/bold green]")
    console.print(f"   * Syntax Valid: [green]{guard_res.syntax_valid}[/green]")
    console.print(f"   * Auto-Fix Attempted: [yellow]{guard_res.auto_fix_attempted}[/yellow]")
    console.print(f"   * Rolled Back: [yellow]{guard_res.rolled_back}[/yellow]")

    # 7. Ashb Rich Terminal Telemetry Dashboard
    console.print(f"\n[bold cyan]5. Real Measured Token Telemetry & Dashboard[/bold cyan]")
    raw_tokens = capsule.token_metrics.raw_context_tokens if capsule.token_metrics else 0
    cap_tokens = capsule.token_metrics.capsule_tokens if capsule.token_metrics else 0

    log_delegation_metrics(
        raw_tokens=raw_tokens,
        capsule_tokens=cap_tokens,
        latency_sec=total_latency_sec,
        status=guard_res.status.value,
        artifact=f"{target_rel_path}:{target_symbol}",
        console=console,
    )

    log_granular_stage_latencies(
        compiler_ms=comp_latency_ms,
        worker_ms=worker_latency_ms,
        guardrail_ms=guard_latency_ms,
        total_ms=total_latency_ms,
        request_id="demo-live-001",
        console=console,
    )

    console.print(Panel(
        "[bold green]DELEGATION COMPLETE[/bold green]\n"
        "Worker completed task within verified code contracts.\n"
        "Repository state preserved without token bloat or summarizer hallucinations.",
        title="[bold green]Final Result[/bold green]",
        border_style="green",
        box=Panel.__dict__.get("box", None) or __import__("rich.box").box.ASCII,
    ))


if __name__ == "__main__":
    main()

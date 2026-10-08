"""
Telemetry and Terminal Dashboard for CapsuleMCP:
Exposes delegation logging and visual live dashboards using Rich.

Required API:
    def log_delegation_metrics(
        raw_tokens: int,
        capsule_tokens: int,
        latency_sec: float,
        status: str,
        artifact: str
    ) -> None
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)


def calculate_token_savings(raw_tokens: int, capsule_tokens: int) -> tuple[int, float]:
    """
    Calculates tokens saved and reduction percentage safely.
    Handles zero raw_tokens edge case without division by zero.
    """
    tokens_saved = max(0, raw_tokens - capsule_tokens)
    if raw_tokens > 0:
        reduction_pct = (tokens_saved / raw_tokens) * 100.0
    else:
        reduction_pct = 0.0
    return tokens_saved, reduction_pct


def format_status_badge(status: str) -> Text:
    """Formats guardrail/delegation status with appropriate style."""
    normalized = status.strip().upper()
    if normalized in ("SUCCESS", "VALID"):
        return Text(normalized, style="bold green")
    elif normalized in ("REPAIRED", "AUTO_REPAIRED"):
        return Text(normalized, style="bold yellow")
    elif "CIRCUIT_BREAKER_TRIPPED" in normalized or normalized in ("FAILED", "ERROR"):
        return Text(normalized, style="bold red")
    else:
        return Text(normalized, style="bold cyan")


def log_delegation_metrics(
    raw_tokens: int,
    capsule_tokens: int,
    latency_sec: float,
    status: str,
    artifact: str,
    console: Optional[Console] = None,
) -> None:
    """
    Ashb Required Telemetry API:
    Renders a live terminal dashboard displaying:
    - Raw context tokens (Naive / Full Context)
    - Capsule tokens (Compiled Context)
    - Tokens saved
    - Reduction percentage (safely calculated)
    - Worker/roundtrip latency
    - Guardrail status
    - Target artifact

    Uses Rich for presentation. Never claims unmeasured savings or hardcodes fake numbers.
    """
    c = console or Console()

    # Safe mathematical calculation of reduction
    tokens_saved, reduction_pct = calculate_token_savings(raw_tokens, capsule_tokens)

    # 1. Summary comparison table: NAIVE vs COMPILED CAPSULE
    table = Table(
        title="[bold cyan]CapsuleMCP Live Delegation Telemetry[/bold cyan]",
        box=box.ASCII,
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("Metric", style="bold white", width=26)
    table.add_column("Naive / Full Context", justify="right", style="dim", width=22)
    table.add_column("Compiled Capsule", justify="right", style="bold cyan", width=22)
    table.add_column("Delta / Impact", justify="right", style="bold green", width=22)

    table.add_row(
        "Token Count",
        f"{raw_tokens:,} tokens",
        f"{capsule_tokens:,} tokens",
        f"-{tokens_saved:,} tokens",
    )
    table.add_row(
        "Context Surface Ratio",
        "100.00%",
        f"{100.0 - reduction_pct:.2f}%",
        f"[bold green]-{reduction_pct:.2f}%[/bold green]",
    )

    # 2. Key execution metrics subtable
    meta_table = Table(box=box.ASCII, show_header=False, expand=True)
    meta_table.add_column("Field", style="bold white", width=24)
    meta_table.add_column("Value", style="cyan")

    meta_table.add_row("Target Artifact", artifact)
    meta_table.add_row("Measured Latency", f"{latency_sec * 1000.0:.2f} ms ({latency_sec:.4f} s)")
    meta_table.add_row("Guardrail Status", format_status_badge(status))

    # Assemble Rich dashboard panel
    dashboard_content = Table.grid(padding=1)
    dashboard_content.add_row(table)
    dashboard_content.add_row(meta_table)

    panel = Panel(
        dashboard_content,
        title="[bold blue]=== CONTEXT IS COMPILED, NOT SUMMARIZED ===[/bold blue]",
        subtitle="[dim]Measured via tiktoken | Zero LLM Summarizer Overhead[/dim]",
        border_style="blue",
        box=box.ASCII,
    )

    c.print(panel)


def log_granular_stage_latencies(
    compiler_ms: float,
    worker_ms: float,
    guardrail_ms: float,
    total_ms: float,
    request_id: str,
    console: Optional[Console] = None,
) -> None:
    """
    Renders compact stage latency telemetry tree.
    """
    c = console or Console()
    tree_text = Text()
    tree_text.append(f"REQUEST {request_id}\n", style="bold magenta")
    tree_text.append("   |\n", style="dim")
    tree_text.append(f"   +-- Compiler   ", style="dim")
    tree_text.append(f"{compiler_ms:>8.2f} ms\n", style="bold cyan")
    tree_text.append(f"   +-- Worker     ", style="dim")
    tree_text.append(f"{worker_ms:>8.2f} ms\n", style="bold yellow")
    tree_text.append(f"   +-- Guardrail  ", style="dim")
    tree_text.append(f"{guardrail_ms:>8.2f} ms\n", style="bold green")
    tree_text.append(f"   +-- Total      ", style="dim")
    tree_text.append(f"{total_ms:>8.2f} ms\n", style="bold white")

    p = Panel(tree_text, title="Stage Latency Breakdown", border_style="cyan", box=box.ASCII)
    c.print(p)

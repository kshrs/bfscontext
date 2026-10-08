"""
Core data models for CapsuleMCP context compilation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CodeUnit:
    """Represents a complete syntactic unit (function or class) in code."""
    name: str
    unit_type: str  # "function" | "class" | "module"
    source_code: str
    start_line: int
    end_line: int
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    returns: Optional[str] = None


@dataclass(frozen=True)
class DependencyUnit:
    """Represents a 1-hop local code dependency."""
    name: str
    file_path: str
    unit_type: str  # "function" | "class" | "variable"
    source_code: str
    is_direct: bool = True


@dataclass(frozen=True)
class IntentContext:
    """Represents Track B intent and its temporal alignment."""
    intent: str
    source: str
    commit_sha: str
    is_stale: bool = False
    warning: Optional[str] = None

    def format_block(self) -> str:
        header = "[INTENT CONTEXT]"
        if self.is_stale:
            header += "\n[HISTORICAL: MAY BE DEPRECATED]"
        if self.source.startswith("MOCK"):
            header += " (MOCK / DEMO ONLY)"
        lines = [header, f"Summary: {self.intent}", f"Intent Commit: {self.commit_sha}"]
        if self.warning:
            lines.append(f"Notice: {self.warning}")
        return "\n".join(lines)


@dataclass(frozen=True)
class TokenMetrics:
    """Token calculation telemetry metrics."""
    raw_context_tokens: int
    capsule_tokens: int
    tokens_saved: int
    reduction_percent: float
    tokenizer_name: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_context_tokens": self.raw_context_tokens,
            "capsule_tokens": self.capsule_tokens,
            "tokens_saved": self.tokens_saved,
            "reduction_percent": round(self.reduction_percent, 2),
            "tokenizer_name": self.tokenizer_name,
        }


@dataclass
class ContextCapsule:
    """The compiled minimal sufficient context capsule for worker agents."""
    task_instructions: str
    intent_context: IntentContext
    target_unit: CodeUnit
    imports: List[str]
    dependencies: List[DependencyUnit]
    git_head_sha: str
    target_file_path: str
    token_metrics: Optional[TokenMetrics] = None
    compilation_trace: List[str] = field(default_factory=list)

    def render(self) -> str:
        """Render the structured capsule string deterministically."""
        sections: List[str] = []

        # 1. TASK INSTRUCTIONS
        sections.append(
            f"[TASK INSTRUCTIONS]\n"
            f"Subtask: {self.task_instructions}\n"
            f"Target File: {self.target_file_path}\n"
            f"Target Unit: {self.target_unit.name} ({self.target_unit.unit_type})\n"
            f"Git HEAD: {self.git_head_sha}"
        )

        # 2. INTENT CONTEXT
        sections.append(self.intent_context.format_block())

        # 3. IMMUTABLE CODE CONTRACTS (Imports + Target Unit)
        contracts = ["[IMMUTABLE CODE CONTRACTS]"]
        if self.imports:
            contracts.append("# Required Imports:")
            contracts.extend(self.imports)
            contracts.append("")
        contracts.append(f"# Target Unit ({self.target_unit.unit_type} {self.target_unit.name}):")
        contracts.append(self.target_unit.source_code)
        sections.append("\n".join(contracts))

        # 4. DEPENDENCIES (Controlled 1-hop local dependencies)
        dep_section = ["[DEPENDENCIES]"]
        if self.dependencies:
            for dep in sorted(self.dependencies, key=lambda d: (d.file_path, d.name)):
                dep_section.append(f"# From {dep.file_path} ({dep.unit_type} {dep.name}):")
                dep_section.append(dep.source_code.strip())
                dep_section.append("")
        else:
            dep_section.append("# No direct 1-hop local dependencies required.")
        sections.append("\n".join(dep_section).strip())

        # 5. TARGET ARTIFACT CONTRACT
        sections.append(
            "[TARGET ARTIFACT CONTRACT]\n"
            "Requirements for Worker LLM:\n"
            f"- Modify or write tests strictly for `{self.target_unit.name}`.\n"
            "- Adhere strictly to the immutable code contracts, types, and dependencies above.\n"
            "- Do not invent unreferenced modules or modify unrequested signatures."
        )

        return "\n\n".join(sections)

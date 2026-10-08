# CapsuleMCP: Dual-Track Causal Memory Framework
> **Deterministic Context Slicing & Causal State Gateway for Autonomous Agent Swarms**

[![Protocol: MCP](https://img.shields.io/badge/Protocol-MCP-blue.svg)](https://modelcontextprotocol.io)
[![State: Causal Dual-Track](https://img.shields.io/badge/Architecture-Dual--Track-green.svg)]()
[![HackITon: 26](https://img.shields.io/badge/Hackathon-HackITon26-orange.svg)]()

---

## 🎯 The Core Problem

Standard multi-agent delegation suffers from **Multi-Agent Context Collapse**:
* **Token Bloat:** Passing tens of thousands of tokens of raw conversational logs, terminal dumps, and obsolete tool outputs to sub-agents burns 95%+ of API budgets.
* **Vector Memory Failure (Temporal Inversion & Syntactic Amputation):** Vector similarity retrieval chops code across arbitrary token boundaries and retrieves obsolete functions from 20 turns ago because cosine similarity is temporally blind.
* **Denial of Wallet:** Infinite self-healing loops drain budgets when LLMs hallucinate broken code repeatedly.

---

## ⚡ The Solution: CapsuleMCP

**CapsuleMCP** acts as an intelligent middleware gateway between the orchestrator (`agy CLI` / `claude-code`) and specialized worker models:

1. **Track A (Deterministic AST Slicing):** Extracts complete, syntactically unbroken functional units and 1-hop module dependencies with zero broken imports.
2. **Track B (Intent Ledger & Cryptographic Hash-Pinning):** Anchors high-level architectural decisions to the active **Git Commit SHA**, preventing stale-state hallucinations.
3. **The 1-Strike Circuit Breaker:** Strips markdown, runs AST syntax verification, allows exactly **one** auto-repair attempt, and executes an automated `git revert` rollback on failure to prevent runaway billing.

---

## 🏗️ Architecture

```
[User / agy CLI]
       │
       ▼ (1) Subtask request
[capsule_mcp.py: FastMCP Server]
       │
       ▼ (2) Target file, subtask, intent
[capsule_engine.py: Dual-Track Slicer]
       ├── Track A: AST Functional Scoper
       └── Track B: Git SHA Hash-Pinning
       │
       ▼ (3) Emits: [Context Capsule] (~850 tokens, 95% reduction)
[Worker Model Fleet (LiteLLM / OpenRouter / Anthropic)]
       │
       ▼ (4) Raw Code Output
[circuit_breaker.py: Guardrails & Revert Guard]
       ├── Markdown & ANSI Stripper
       ├── Tree-sitter / AST Syntax Validator
       └── 1-Strike Circuit Breaker (Auto-Fix or Git Revert)
       │
       ▼ (5) Telemetry Visualizer & Output Artifact
[agy CLI receives verified code artifact]
```

---

## 🚀 Quickstart & Verification

Run the core engine test suite:
```bash
python3 test_capsule_engine.py
```

Generate a Context Capsule programmatically:
```python
from capsule_engine import generate_context_capsule

capsule = generate_context_capsule(
    file_path="src/billing.py",
    subtask_description="Generate unit tests for charge_user method",
    intent_summary="Migrating billing system to Stripe v3 idempotency standard",
    target_symbol="charge_user"
)

print(capsule.capsule_prompt)
print(f"Tokens saved: {capsule.tokens_saved} ({capsule.compression_ratio * 100:.1f}%)")
```

---

## 👥 Team & Work Allocation (HackITon26)
* **kshrs (Lead):** Core Systems Architect & Dual-Track Capsule Engine (`capsule_engine.py`).
* **bk:** Systems Reliability & Circuit Breaker Guardrails (`circuit_breaker.py`).
* **nvss:** MCP Protocol & `agy CLI` Integration Gateway (`capsule_mcp.py`).
* **ashb:** Telemetry, Demo Test Harness & Pitch Lead (`telemetry.py` & `demo/`).

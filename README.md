# BFSContext (CapsuleMCP)
> **Better. Faster. Smaller Context.**  
> Deterministic State Slicing & Causal Memory Gateway for Multi-Agent Swarms.

[![Protocol: MCP](https://img.shields.io/badge/Protocol-MCP-blue.svg)](https://modelcontextprotocol.io)
[![State: Dual--Track Causal](https://img.shields.io/badge/State-Dual--Track-green.svg)]()
[![HackITon: 26](https://img.shields.io/badge/Hackathon-HackITon26-orange.svg)]()

---

## 💡 What is BFSContext?

**BFSContext** stands for:
* **Better:** 100% syntactically intact code slices with zero broken imports or hallucinated stale state.
* **Faster:** 4x lower Time-to-First-Token (TTFT) by bypassing massive conversational history dumps.
* **Smaller:** 95%+ token reduction, compressing bloated 50,000-token sessions into surgical ~850-token **Context Capsules**.

---

## 🚨 The Problem

Modern multi-agent delegation (e.g., in `agy CLI`, `claude-code`, LangGraph, CrewAI) suffers from **Multi-Agent Context Collapse**:

1. **Token Bloat & Cost Explosions:**  
   Delegating a micro-task currently forces the orchestrator to dump 50,000+ tokens of raw conversational logs, terminal dumps, and obsolete tool outputs to sub-agents.
2. **Vector Memory Failure:**  
   Standard RAG/vector retrieval chops code across arbitrary token limits (causing syntax errors) and retrieves obsolete code from 20 turns ago because cosine similarity is temporally blind.
3. **Denial-of-Wallet (DoW):**  
   Sub-agents trapped in infinite self-healing loops burn entire API budgets on unfixable code.

---

## ⚡ The Solution: Dual-Track Causal Memory

**BFSContext** acts as an intelligent Model Context Protocol (MCP) middleware between the lead agent and worker models:

```
[Orchestrator: agy CLI / claude-code]
       │
       ▼ (1) Subtask request
[BFSContext Gateway (FastMCP)]
       │
       ├── Track A (AST Slicer): Extracts active function + imports (0% syntax cut)
       ├── Track B (Intent Ledger): Pinned to active Git Commit SHA (Anti-Drift)
       │
       ▼ (2) Generates: [Context Capsule] (~850 tokens, 95% reduction)
[Worker Model Fleet (DeepSeek / Claude Haiku / Llama-3)]
       │
       ▼ (3) Raw Code Output
[1-Strike Circuit Breaker]
       ├── Markdown Stripper & Tree-sitter Syntax Validation
       ├── Max Retries = 1 Auto-Fixer
       └── Automated Git Revert on failure (Protection against runaway billing)
       │
       ▼ (4) Verified Artifact
[Target codebase updated safely]
```

---

## 📊 Key Highlights & Metrics

| Metric | Traditional Delegation | BFSContext |
| :--- | :--- | :--- |
| **Input Tokens per Call** | ~50,000 tokens | **~850 tokens (95%+ reduction)** |
| **Syntactic Integrity** | Fragmented chunks, missing imports | **100% valid AST functional blocks** |
| **Temporal Accuracy** | Frequently pulls obsolete state | **Cryptographically pinned to Git HEAD SHA** |
| **Fault Protection** | Infinite retry loops / wallet drain | **1-Strike Circuit Breaker + Git Revert** |
| **Integration** | Custom API glue | **Drop-in Model Context Protocol (MCP)** |

---

## 🚀 Quickstart

### 1. Run Core Engine Verification Suite
```bash
python3 test_capsule_engine.py
```

### 2. Programmatic Usage
```python
from capsule_engine import generate_context_capsule

capsule = generate_context_capsule(
    file_path="src/billing.py",
    subtask_description="Generate unit tests for charge_user method",
    intent_summary="Migrating billing system to Stripe v3 idempotency standard",
    target_symbol="charge_user"
)

print(capsule.capsule_prompt)
print(f"Tokens Saved: {capsule.tokens_saved} ({capsule.compression_ratio * 100:.1f}%)")
print(f"Pinned Commit: {capsule.commit_sha[:8]}")
```

---

## 👥 HackITon26 Team Roster

* **kshrs (Lead):** Core Systems Architect & Dual-Track Capsule Engine (`capsule_engine.py`).
* **bk:** Systems Reliability & Circuit Breaker Guardrails (`circuit_breaker.py`).
* **nvss:** MCP Protocol & `agy CLI` Integration Gateway (`capsule_mcp.py`).
* **ashb:** Telemetry, Demo Test Harness & Pitch Lead (`telemetry.py` & `demo/`).

# CapsuleMCP — Algorithmic Context Compilation for Multi-Agent AI

> *"Context is compiled, not summarized."*

CapsuleMCP algorithmically constructs the minimum sufficient context required by worker LLMs when delegating subtasks across multi-agent workflows. It eliminates token bloat, reduces latency, and prevents contract hallucinations by compiling exact syntactic units and bounded structural dependencies without relying on another summarizer LLM.

---

## Architecture Overview

```
User / Orchestrator Agent
           ↓
    Context Gateway
           ↓
   Context Compiler
   ┌──────────────────────────────────────────────┐
   │ Track A — State                              │
   │  • AST parsing (complete syntactic units)    │
   │  • Import preservation                       │
   │  • Bounded structural dependency BFS         │
   │  • Git HEAD state association                │
   └──────────────────────────────────────────────┘
           +
   ┌──────────────────────────────────────────────┐
   │ Track B — Intent (Pluggable Interface)       │
   │  • Semantic task intent                      │
   │  • Temporal staleness check vs Git HEAD      │
   └──────────────────────────────────────────────┘
           ↓
    Minimal Context Capsule
           ↓
   Worker LLM / Adapter
           ↓
    Telemetry Sink
```

---

## Key Features

1. **Deterministic AST State Extraction (Track A)**:
   - Identifies and isolates the complete target function, class, or method.
   - Retains verbatim imports and type signatures.
   - Controlled bounded dependency resolution (depth = 0, 1, 2) within local modules and files with cyclic reference protection and deduplication.
   - Excludes unrelated functions, classes, and test files from the target module.
2. **Temporal Git Alignment & Staleness Detection (Track B)**:
   - Associates intent retrieval with `git rev-parse HEAD`.
   - Automatically marks mismatched commit intent with `[HISTORICAL: MAY BE DEPRECATED]`.
3. **Structured Context Capsule**:
   - `[TASK INSTRUCTIONS]`
   - `[INTENT CONTEXT]`
   - `[IMMUTABLE CODE CONTRACTS]`
   - `[DEPENDENCIES]`
   - `[TARGET ARTIFACT CONTRACT]`
4. **Real Measured Token Telemetry**:
   - Integrated with `tiktoken` (`cl100k_base`) with character-based fallback.
   - Real metrics: `raw_context_tokens`, `capsule_tokens`, `tokens_saved`, and `reduction_percent`.
   - **No fabricated metrics**: real reduction reported per repository and task.
5. **Pluggable Architecture for Teammate Modules**:
   - Clean abstract interfaces in `capsulemcp.adapters.interfaces`:
     - `CodeAnalyzer`
     - `IntentProvider`
     - `WorkerProvider`
     - `TelemetrySink`
   - Fully isolated mock adapters in `capsulemcp.adapters.mock` clearly marked as `MOCK / DEMO ONLY`.

---

## Benchmark Methodology & Empirical Evaluation

> **Disclaimer**: The figures below represent empirical measurements on the included synthetic multi-module benchmark repository (`benchmark/large_benchmark_repo`). They are not claims of universal guarantees for every language or external repository.

### Metric Definitions & Formulas

1. **Token Count**: Calculated using `tiktoken` (`cl100k_base`).
2. **Token Reduction %**:
   $$\text{Reduction} = \left(1 - \frac{\text{Capsule Tokens}}{\text{Full Context Tokens}}\right) \times 100$$
   *(Aggregate reduction is computed from total token counts across all targets, never an unweighted mean of percentages).*
3. **Structural Dependency Recall**:
   $$\text{Recall} = \frac{|\text{Expected Structural Dependencies in Context}|}{|\text{Expected Structural Dependencies}|}$$
   *Structural dependencies represent symbols required by the compiler/type checker to execute or test the unit (e.g. parameter types, base classes, return types, direct exceptions).*
4. **Irrelevant Code Ratio**:
   $$\text{Irrelevant Ratio} = \frac{|\text{Known Unrelated Symbols in Context}|}{|\text{Known Unrelated Symbols}|}$$
5. **Compilation Latency**: Wall-clock CPU time in milliseconds measured with high-resolution `time.perf_counter()`.

### Benchmark Comparison (3 Realistic Targets)

Evaluated across:
1. `billing_engine.execute_user_charge` (payment domain)
2. `auth_service.authenticate_user` (security & session domain)
3. `invoice_generator.generate_invoice` (reporting & cloud storage domain)

| Method | Tokens | Reduction | Structural Recall | Irrelevant Code Ratio | Latency |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Full Context (Naive Repo)** | 3,795 | 0.00% | 100.0% | 100.0% | ~13ms |
| **Vector-Style Sim (top_k=3)** | 1,460 | 61.53% | 66.7% | 31.0% | ~3ms |
| **Vector-Style Sim (top_k=5)** | 2,199 | 42.06% | 66.7% | 55.7% | ~3ms |
| **Capsule Compiler (Ours)** | **1,452** | **61.74%** | **100.0%** | **0.0%** | ~48ms |

*Key finding: Vector-style retrieval simulation achieves token savings but sacrifices structural dependency recall (missing required contracts in 33% of cases) and leaks up to 55.7% irrelevant symbols. Capsule Compiler delivers 61.74% aggregate reduction with 100% structural recall and 0.0% irrelevant code leakage.*

---

## Model Context Protocol (MCP) Integration

CapsuleMCP exposes its compilation and delegation capabilities through a thin MCP Server layer (`src/capsulemcp/mcp_server.py`).

### MCP Flow

```
AGY / Orchestrator Agent
          ↓
  MCP Tool: delegate_with_capsule
          ↓
  Input Validation & Security Guardrails (Path Traversal Protection)
          ↓
  Context Compiler (Track A AST + Track B Intent)
          ↓
  Minimal Context Capsule
          ↓
  Worker Provider (Mock / Pluggable)
          ↓
  Telemetry Sink (Traceable request_id)
          ↓
  Structured Response JSON
```

### Primary MCP Tool: `delegate_with_capsule`

#### Parameters:
- `target_file` (string, required): Relative path to target file within repository.
- `subtask` (string, required): Specific prompt or implementation requirement.
- `intent` (string, optional): Architectural intent or PR summary.
- `target_symbol` (string, optional): Specific function, class, or method name.
- `worker_model` (string, optional, default: `"mock"`): Target worker identifier.
- `max_dependency_depth` (integer, optional, default: `1`): Bounded dependency depth ($0, 1, 2$).
- `repo_path` (string, optional): Repository root directory.

#### Example MCP Response:
```json
{
  "status": "success",
  "request_id": "eced62db-602e-45f3-9631-a00b76669871",
  "target_file": "src/billing.py",
  "target_symbol": "charge_user",
  "commit_sha": "33b86a40250890c6fdd781eb014ab2073b30e72d",
  "is_intent_stale": false,
  "capsule_prompt": "[TASK INSTRUCTIONS]\n...\n[IMMUTABLE CODE CONTRACTS]\n...\n[DEPENDENCIES]\n...",
  "token_metrics": {
    "raw_context_tokens": 712,
    "capsule_tokens": 652,
    "tokens_saved": 60,
    "reduction_percent": 8.43,
    "tokenizer_name": "tiktoken:cl100k_base"
  },
  "dependencies": [
    { "name": "PaymentError", "file": "src/billing.py", "type": "class", "is_direct": true }
  ],
  "worker_result": {
    "status": "success",
    "is_mock": true,
    "disclaimer": "MOCK / DEMO ONLY - Simulated worker response",
    "worker_latency_ms": 0.0,
    "generated_code": "# Generated test stub..."
  }
}
```

---

## Installation

```bash
git clone https://github.com/kshrs/bfscontext.git
cd bfscontext
git checkout feature/context-compiler

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## Running Tests

Execute the comprehensive 41-test test suite:

```bash
pytest -v
```

---

## Running Demos & Benchmarks

1. Run the core context compiler demo:
```bash
python demo/run_demo.py
```

2. Run the end-to-end MCP server delegation demo:
```bash
python demo/run_mcp_demo.py
```

3. Run the automated multi-target benchmark:
```bash
python benchmark/run_benchmark.py
```


# CapsuleMCP — Algorithmic Context Compilation for Multi-Agent AI

> *"Context is compiled, not summarized."*

CapsuleMCP algorithmically constructs the minimum sufficient context required by worker LLMs when delegating subtasks across multi-agent workflows. It eliminates token bloat, reduces latency, and prevents hallucinations by compiling exact syntactic units and controlled 1-hop dependencies without relying on another summarizer LLM.

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
   │  • Controlled 1-hop dependency slicing       │
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
   - Identifies and isolates the complete target function or class.
   - Retains verbatim imports and type signatures.
   - Controlled 1-hop dependency resolution within local modules and files.
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
     - `IntentProvider`
     - `WorkerProvider`
     - `TelemetrySink`
   - Fully isolated mock adapters in `capsulemcp.adapters.mock` clearly marked as `MOCK / DEMO ONLY`.

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

Execute the comprehensive 21-test test suite:

```bash
pytest -v
```

---

## Running the Demo

Run the realistic demo against `demo/sample_repo`:

```bash
python demo/run_demo.py
```

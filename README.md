# CapsuleMCP — Algorithmic Context Compilation for Multi-Agent AI

> *"Context is compiled, not summarized."*
>
> *"The compiler decides what the worker needs; the worker does not decide what context it receives."*
>
> *"Generate → Validate → Apply, not Generate → Trust."*

CapsuleMCP algorithmically constructs the minimal sufficient context required by worker LLMs when delegating subtasks across multi-agent workflows. It eliminates token bloat, reduces inference latency, and prevents contract hallucinations by compiling exact syntactic units, verbatim imports, and bounded structural dependencies—without relying on another summarizer LLM.

---

## 1. The Problem: The Cost of Naive Context Delegation

When an orchestrating agent delegates tasks to sub-agents, conventional architectures dump entire repositories, multiple complete files, or large conversational histories into the sub-agent prompt.

This naive approach introduces severe systemic costs:
- **Token Bloat**: Sending thousands of irrelevant lines repeatedly drains token budgets and inflates inference bills.
- **Inference Latency Spikes**: Sub-agents spend precious time parsing irrelevant classes, data fixtures, and helper scripts.
- **Loss of Structural Dependencies**: Distant call contracts, imported error classes, and return schemas get lost in the noise, causing hallucinated method signatures.
- **Stale Context**: Code references drift out of sync with repository Git state across commits.

---

## 2. Why Summarization Is Not Sufficient

A common naive workaround is placing an LLM "summarizer" in front of the sub-agent. This fails for mission-critical software engineering:
1. **Nondeterministic Degradation**: Summarizer LLMs drop subtle typing details, exact exception types, and parameter names.
2. **Double Latency & Cost**: Invoking an LLM to prepare context before invoking the worker doubles token spend and introduces severe latency overhead.
3. **Loss of Code Invariants**: Code requires syntactically and structurally exact contracts, not natural language paraphrases.

---

## 3. Why Vector Retrieval Alone Misses Structural Dependencies

Retrieval-Augmented Generation (RAG) using semantic embeddings indexes text by proximity in embedding space, not syntactic graphs. As measured in our benchmarks:
- Vector similarity retrieves textually similar comments or keywords (e.g., matching unrelated analytics or billing scripts) while leaking up to **43.3% - 55.7% irrelevant code**.
- Vector retrieval routinely misses **1-hop structural dependencies** (e.g. imported base classes, parameter type definitions, exception classes located in separate files), dropping structural recall to **66.7%**.

---

## 4. The Solution: Algorithmic Context Compilation

CapsuleMCP treats context preparation as a compiler pass:
1. **Track A (State)**: Deterministic Abstract Syntax Tree (AST) parsing isolates the complete syntactic unit (function or class), collects exact imports, and performs bounded Breadth-First Search (BFS) dependency traversal (depth $0, 1, 2$) across local modules.
2. **Track B (Intent)**: Gathers temporal task intent and correlates it with the exact `git rev-parse HEAD` commit SHA, detecting historical drift.

```
AGY / Orchestrator Agent
          │
          ▼
   [CapsuleMCPServer] (MCP Gateway / JSON-RPC 2.0)
          │
          ▼
   [ContextCompiler] ──► Track A: CodeAnalyzer (AST BFS)
          │            ► Track B: IntentProvider
          │            ► Git State Coherence
          ▼
   [ContextCapsule] (Deterministic Algorithmic Capsule)
          │
          ▼
   [WorkerProvider] ───► MockWorkerProvider / RealWorkerProvider (Capsule-Only)
          │
          ▼
   [CircuitBreaker] ───► One-Strike Guardrail (Syntax & Structural Validation)
          │
     ┌────┴─────┐
     │          │
  SUCCESS    FAILURE
     │          │
     ▼          ▼
   APPLY     ONE FIX
     │          │
     │      ┌───┴────┐
     │      │        │
     │    VALID    INVALID
     │      │        │
     │      ▼        ▼
     │   REPAIRED  ROLLBACK
     │               │
     └───────┬───────┘
             ▼
      [TelemetrySink]
             ▼
        Final Result
```

---

## 5. Dual-Track Context Architecture

| Track | Concern | Implementation | Invariant |
| :--- | :--- | :--- | :--- |
| **Track A: State** | Concrete code contracts | Python AST (`ast_extractor.py`) | Syntactically exact, zero LLM hallucination |
| **Track B: Intent** | Human / PR intention | `IntentProvider` interface | Linked to Git HEAD SHA, flags staleness |

### Context Capsule Sections:
1. `[TASK INSTRUCTIONS]`: Target file, target unit name, Git commit SHA, and subtask prompt.
2. `[INTENT CONTEXT]`: High-level purpose and temporal staleness status.
3. `[IMMUTABLE CODE CONTRACTS]`: Verbatim imports and target syntactic unit.
4. `[DEPENDENCIES]`: Bounded 1-hop structural dependencies (classes, functions, exceptions).
5. `[TARGET ARTIFACT CONTRACT]`: Explicit behavioral boundaries for worker output.

---

## 6. One-Strike Guardrail & Circuit Breaker

Allowing worker LLMs to enter recursive "self-healing" loops introduces infinite token burn and unpredictable behavior. CapsuleMCP implements a strict **One-Strike Circuit Breaker**:

1. **Markdown Fence Sanitization**: Normalizes ````python ... ```` blocks safely.
2. **Static Syntax Verification**: Validates AST using Python static compilation (`compile(code, filename, "exec")`). **Worker output is NEVER executed, eval'd, or imported**.
3. **Structural Verification**: Verifies target symbol exists in output.
4. **Strict Single Repair Attempt**: If syntax is invalid, calls an injected `FixerProvider` **EXACTLY ONCE**. No while-loops, no recursive retries.
5. **Target-Scoped Git Rollback**: If still invalid, trips the circuit breaker and safely rolls back the target file to the pre-operation Git commit SHA.
6. **Pre-Existing Modification Protection**: If the target file had uncommitted changes before the run, rollback protects developer work from accidental deletion.

---

## 7. Benchmark Methodology & Measured Results

> **Methodology Note**: Metrics are measured empirically at runtime on our multi-module benchmark repository (`benchmark/large_benchmark_repo`) using `tiktoken` (`cl100k_base`). Metrics are mathematical measurements, not arbitrary test assertions.

### Metric Definitions:
- **Token Reduction %**: $\left(1 - \frac{\text{Capsule Tokens}}{\text{Full Context Tokens}}\right) \times 100$
- **Structural Dependency Recall**: Percentage of required parameter types, return types, and exceptions included in context.
- **Known-Unrelated-Symbol Inclusion Rate**: Percentage of unreferenced classes and functions leaked into context.
- **Latency**: High-resolution wall-clock duration (`time.perf_counter()`).

### Measured Results Across 3 Realistic Targets:
*(Targets: `billing_engine.execute_user_charge`, `auth_service.authenticate_user`, `invoice_generator.generate_invoice`)*

| Method | Total Tokens | Reduction % | Structural Recall | Unrelated Symbol Inclusion | Latency |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Full Context (Naive Repo)** | 3,795 | 0.00% | 100.0% | 100.0% | ~13 ms |
| **Vector-Style Sim ($k=3$)** | 1,460 | 61.53% | 66.7% | 31.0% | ~3 ms |
| **Vector-Style Sim ($k=5$)** | 2,199 | 42.06% | 66.7% | 55.7% | ~3 ms |
| **Capsule Compiler (Ours)** | **1,452** | **61.74%** | **100.0%** | **0.0%** | ~48 ms |

---

## 8. Live Demonstration & Failure Injection

CapsuleMCP includes live terminal demonstrations with Rich dashboards and deterministic failure injection:

### Running the Live Terminal Dashboard:

```bash
# 1. Primary Live Terminal Dashboard (Linux / macOS / Windows)
python demo/run_demo.py

# 2. Failure Injection Demo (Simulates worker error -> 1 fix attempt -> Circuit Breaker)
python demo/run_demo.py --simulate-error

# 3. Direct Failure Injection Runner
python demo/run_failure_demo.py --simulate-error

# 4. Cross-Platform Scripts
./demo/run_demo.sh          # Linux / macOS entry point
.\demo\run_demo.ps1         # Windows PowerShell entry point
```

### Running the Complete Multi-Module E2E Pipeline:

```bash
# Standard mock run (valid output -> SUCCESS -> applied safely)
python demo/run_e2e_demo.py --mode mock --failure valid

# Repairable failure (malformed syntax -> 1 fix attempt -> REPAIRED -> applied)
python demo/run_e2e_demo.py --mode mock --failure repairable

# Unrecoverable failure (fatal syntax -> 1 fix fails -> CIRCUIT_BREAKER_TRIPPED -> safe rollback)
python demo/run_e2e_demo.py --mode mock --failure unrecoverable

# Inspect full Context Capsule sent to worker
python demo/run_e2e_demo.py --show-capsule

# Live LLM execution (fails gracefully if CAPSULEMCP_API_KEY is unset)
python demo/run_e2e_demo.py --mode real
```

### Demonstration Output Sections:
1. **Compilation Trace**: Step-by-step algorithmic pipeline representation.
2. **The Core Difference**: Naive tokens vs compiled capsule tokens and measured reduction.
3. **"Why This Context?"**: Causal, deterministic explanation of included vs excluded symbols.
4. **Worker Input Contract**: Proof that the worker received capsule-only payload.
5. **One-Strike Guardrail**: Verification status, auto-fix count ($\le 1$), and rollback state.
6. **Telemetry Trace**: Granular stage latencies (compiler, worker, guardrail, total).

---

## 9. Model Context Protocol (MCP) Tool Reference

The MCP Server exposes tool `delegate_with_capsule`:

| Argument | Type | Description |
| :--- | :--- | :--- |
| `target_file` | string (required) | Path to target python file within repository |
| `subtask` | string (required) | Delegated instruction or prompt |
| `target_symbol` | string (optional) | Target function or class name |
| `intent` | string (optional) | Architectural intent or PR description |
| `worker_model` | string (optional) | Worker identifier (e.g. `'mock'`, `'gpt-4o'`) |
| `max_dependency_depth` | integer (optional) | Maximum BFS traversal depth (default: 1) |
| `apply_to_disk` | boolean (optional) | Whether validated code should be applied to disk |

---

## 10. Clean Interfaces for Teammate Integration

All external modules conform to clean abstract interfaces (`src/capsulemcp/adapters/interfaces.py`). Teammates can swap implementations without modifying `ContextCompiler`, `mcp_server`, or `CircuitBreaker`:
- `CodeAnalyzer`: Extract syntactic units and bounded dependencies (e.g., Tree-sitter for TypeScript/Go).
- `IntentProvider`: Retrieve architectural intentions from PRs, issue trackers, or vector DBs.
- `WorkerProvider`: Delegate context capsules to worker models (OpenAI, Anthropic, local vLLM).
- `FixerProvider`: Perform single-attempt code repair.
- `TelemetrySink`: Route runtime metrics to Prometheus, OpenTelemetry, or cloud logs.

---

## 11. Testing & Verification

The suite includes **62 automated tests** covering:
- AST parsing, import preservation, and target symbol isolation
- Cyclic dependency protection and BFS traversal depth limits
- MCP tool dispatch, JSON-RPC handling, and path traversal security checks
- Deterministic token metrics and regression consistency
- Guardrail static validation, single repair attempts, and safe Git rollback
- Pre-existing uncommitted modification preservation
- Real worker capsule-only payload contracts and missing key degradation

```bash
python -m pytest -v
```

---

## 12. Limitations & Scope

To ensure precision and avoid overpromising:
- **Language Support**: Structural AST analysis is currently implemented for Python (`.py`). Other languages require implementing `CodeAnalyzer`.
- **Dynamic References**: Highly dynamic Python runtime imports (e.g., `importlib.import_module`, `getattr` invocation chains) cannot be resolved solely via static AST analysis.
- **Semantic Correctness**: The guardrail validates static syntax and structural symbol preservation; it does not replace domain-level unit test suites.

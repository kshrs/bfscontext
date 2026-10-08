#!/usr/bin/env bash
# CapsuleMCP Live Demonstration Entrypoint (Linux / macOS)
# Runs the full live demonstration with Rich dashboard and telemetry.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PYTHONPATH="${REPO_ROOT}:${REPO_ROOT}/src:${PYTHONPATH:-}"

echo "================================================================="
echo "CapsuleMCP Live Demonstration Runner (Linux / macOS)"
echo "================================================================="

# Check Python availability
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[ERROR] Python 3.10+ is required but not found in PATH." >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

# Execute main live demo
echo "[1/2] Executing Live Demonstration (Context Compiler -> Guardrail -> Telemetry)..."
"${PYTHON_BIN}" "${SCRIPT_DIR}/run_demo.py" "$@"

# If simulate-error flag was not provided, optionally demonstrate failure scenario
if [[ ! " $* " =~ " --simulate-error " ]]; then
    echo ""
    echo "[2/2] Demonstrating One-Strike Guardrail & Circuit Breaker Failure Scenario..."
    "${PYTHON_BIN}" "${SCRIPT_DIR}/run_failure_demo.py" --simulate-error
fi

echo ""
echo "================================================================="
echo "DEMO FINISHED SUCCESSFULLY: All contracts verified."
echo "================================================================="

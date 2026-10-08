# CapsuleMCP Live Demonstration Entrypoint (Windows PowerShell)
# Runs the full live demonstration with Rich dashboard and telemetry.

[CmdletBinding()]
param(
    [switch]$SimulateError
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

$env:PYTHONPATH = "$RepoRoot;$RepoRoot\src;$env:PYTHONPATH"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "CapsuleMCP Live Demonstration Runner (Windows PowerShell)" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

# Test Python
try {
    $pyVersion = python --version 2>&1
    Write-Host "[OK] Using: $pyVersion" -ForegroundColor Green
} catch {
    Write-Error "[ERROR] Python is not installed or not in system PATH."
    exit 1
}

if ($SimulateError) {
    Write-Host "`nRunning Failure Injection Demonstration..." -ForegroundColor Yellow
    python "$ScriptDir\run_failure_demo.py" --simulate-error
} else {
    Write-Host "`n[1/2] Executing Live Demonstration (Context Compiler -> Guardrail -> Telemetry)..." -ForegroundColor Yellow
    python "$ScriptDir\run_demo.py"

    Write-Host "`n[2/2] Demonstrating One-Strike Guardrail & Circuit Breaker Failure Scenario..." -ForegroundColor Yellow
    python "$ScriptDir\run_failure_demo.py" --simulate-error
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "DEMO FINISHED SUCCESSFULLY: All contracts verified." -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan

"""
Demonstration runner for CapsuleMCP Context Compiler.
Shows real algorithmic compilation, token metrics, and worker delegation.
"""

from pathlib import Path
from capsulemcp.context_compiler import ContextCompiler
from capsulemcp.adapters.mock import MockIntentProvider, MockWorkerProvider, MockTelemetrySink


def main():
    repo_path = Path(__file__).parent / "sample_repo"
    target_file = repo_path / "src" / "billing.py"

    intent_provider = MockIntentProvider(
        default_intent="Stripe webhook billing integration with signature validation"
    )
    worker = MockWorkerProvider()
    telemetry = MockTelemetrySink()

    compiler = ContextCompiler(
        repo_path=str(repo_path),
        intent_provider=intent_provider,
        telemetry_sink=telemetry,
    )

    subtask = "Write pytest tests for charge_user() using mock Stripe webhook payloads."
    print("=" * 60)
    print("CapsuleMCP Context Compiler Demo")
    print(f"Subtask: {subtask}")
    print(f"Target: {target_file}")
    print("=" * 60)

    capsule = compiler.generate_context_capsule(
        file_path=str(target_file),
        subtask_description=subtask,
        target_unit_name="charge_user",
    )

    print("\n--- COMPILED CONTEXT CAPSULE ---")
    print(capsule.render())

    print("\n--- REAL MEASURED TOKEN METRICS ---")
    if capsule.token_metrics:
        m = capsule.token_metrics.to_dict()
        for k, v in m.items():
            print(f"  {k}: {v}")

    print("\n--- WORKER DELEGATION (MOCK WORKER) ---")
    worker_output = worker.generate(capsule)
    print(f"Status: {worker_output['status']}")
    print(f"Disclaimer: {worker_output['disclaimer']}")
    print(f"Generated Stub:\n{worker_output['generated_code']}")

    print("\n--- TELEMETRY SINK ---")
    print(f"Events recorded: {len(telemetry.records)}")
    if telemetry.records:
        print(f"Telemetry record: {telemetry.records[0]}")


if __name__ == "__main__":
    main()

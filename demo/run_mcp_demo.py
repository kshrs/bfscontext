"""
End-to-end Demonstration of CapsuleMCP Server Delegation Flow:
AGY / Main Agent -> MCP Server (delegate_with_capsule) -> Context Compiler -> Context Capsule -> Mock Worker -> Result
"""

from pathlib import Path
import json
from capsulemcp.mcp_server import CapsuleMCPServer
from capsulemcp.adapters.mock import MockTelemetrySink, MockWorkerProvider, MockIntentProvider


def main():
    repo_path = Path(__file__).parent / "sample_repo"
    telemetry = MockTelemetrySink()
    worker = MockWorkerProvider()
    intent_provider = MockIntentProvider(
        default_intent="Stripe webhook billing integration with signature validation"
    )

    server = CapsuleMCPServer(
        repo_path=str(repo_path),
        intent_provider=intent_provider,
        telemetry_sink=telemetry,
        worker_provider=worker,
    )

    print("=" * 90)
    print("CAPSULEMCP SERVER END-TO-END DELEGATION DEMONSTRATION")
    print("=" * 90)

    task_payload = {
        "target_file": "src/billing.py",
        "subtask": "Write pytest tests for charge_user() using mock Stripe webhook payloads.",
        "target_symbol": "charge_user",
        "intent": "Implement idempotent user charge handling and webhook signature verification",
        "worker_model": "mock-claude-worker",
        "max_dependency_depth": 1,
    }

    print("\n1. AGY / Main Agent issues MCP tool call:")
    print(f"Tool: {server.TOOL_NAME}")
    print("Arguments:")
    print(json.dumps(task_payload, indent=2))

    # Invoke MCP tool
    response = server.delegate_with_capsule(**task_payload)

    print("\n2. MCP Server Execution & Context Compilation:")
    print(f"Status:       {response['status']}")
    print(f"Request ID:   {response['request_id']}")
    print(f"Target Unit:  {response['target_symbol']} ({response['target_file']})")
    print(f"Git HEAD SHA: {response['commit_sha']}")
    print(f"Intent Stale: {response['is_intent_stale']}")

    print("\n3. Real Measured Token Metrics:")
    tm = response["token_metrics"]
    for k, v in tm.items():
        print(f"  {k}: {v}")

    print("\n4. Extracted Structural Dependencies (Controlled 1-hop):")
    for dep in response["dependencies"]:
        print(f"  - [{dep['type']}] {dep['name']} (from {dep['file']}, direct={dep['is_direct']})")

    print("\n5. Compiled Context Capsule Delivered to Worker:")
    print("-" * 80)
    print(response["capsule_prompt"])
    print("-" * 80)

    print("\n6. Worker Provider Output:")
    w = response["worker_result"]
    print(f"Worker Status:      {w['status']}")
    print(f"Worker Disclaimer:  {w['disclaimer']}")
    print(f"Worker Latency:     {w['worker_latency_ms']} ms")
    print(f"Generated Code:\n{w['generated_code']}")

    print("7. Telemetry Sink Record:")
    print(f"Records captured: {len(telemetry.records)}")
    if telemetry.records:
        print(json.dumps(telemetry.records[0], indent=2))

    print("\n" + "=" * 90)
    print("DEMO COMPLETE: Worker received MINIMAL SUFFICIENT CONTEXT without full repository bloat.")
    print("=" * 90)


if __name__ == "__main__":
    main()

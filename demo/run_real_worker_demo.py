"""
Real Worker Demonstration:
Delegates task with compiled Context Capsule to RealWorkerProvider (or instructs on API key configuration).
Shows:
1. Compilation of Context Capsule
2. Sending ONLY the capsule to the real worker (never raw uncompiled repo)
3. One-strike circuit breaker evaluation
4. Latency breakdown (compilation, worker, guardrail, total)
"""

import os
from pathlib import Path
from capsulemcp.adapters.real_worker import RealWorkerProvider
from capsulemcp.mcp_server import CapsuleMCPServer


def main():
    repo_path = Path(__file__).parent / "sample_repo"
    target_file = "src/billing.py"
    target_symbol = "charge_user"
    subtask = "Implement robust retry logic for charge_user() handling transient database errors."

    print("=" * 90)
    print("CAPSULEMCP REAL WORKER PROVIDER DEMONSTRATION")
    print("Central Principle: The worker receives COMPILED CONTEXT, not the whole repository.")
    print("=" * 90)

    # Check for API key
    api_key = os.getenv("CAPSULEMCP_API_KEY")
    model = os.getenv("CAPSULEMCP_MODEL", "gpt-4o-mini")

    if not api_key:
        print("\n[NOTE]: No CAPSULEMCP_API_KEY detected in environment.")
        print("To run against a live OpenAI or compatible LLM provider:")
        print("  1. Set environment variables:")
        print("     $env:CAPSULEMCP_API_KEY = 'sk-...'")
        print("     $env:CAPSULEMCP_MODEL   = 'gpt-4o-mini'  (optional, defaults to gpt-4o-mini)")
        print("     $env:CAPSULEMCP_BASE_URL= 'https://api.openai.com/v1'  (optional)")
        print("  2. Run: python demo/run_real_worker_demo.py\n")
        print("Running in graceful configuration mode with RealWorkerProvider contract verification...")

        # Run RealWorkerProvider in unconfigured mode to demonstrate graceful failure handling
        worker = RealWorkerProvider()
        server = CapsuleMCPServer(repo_path=str(repo_path), worker_provider=worker)
        res = server.delegate_with_capsule(
            target_file=target_file,
            subtask=subtask,
            target_symbol=target_symbol,
            worker_model="real-llm",
        )
        print("\nGraceful Real-Worker Error Response:")
        print(f"Status:             {res['status']}")
        print(f"Worker Error:       {res['worker_result'].get('error')}")
        print(f"Guardrail Status:   {res['guardrail']['status']}")
        print("Circuit breaker protected repository: NO WRITES OCCURRED.")
        print("=" * 90)
        return

    print(f"\n[CONFIGURED]: Real Worker Provider initialized with model: {model}")
    real_worker = RealWorkerProvider(api_key=api_key, model=model)
    server = CapsuleMCPServer(repo_path=str(repo_path), worker_provider=real_worker)

    res = server.delegate_with_capsule(
        target_file=target_file,
        subtask=subtask,
        target_symbol=target_symbol,
        worker_model=model,
    )

    print("\n1. MCP Delegation Result:")
    print(f"Status:       {res['status']}")
    print(f"Request ID:   {res['request_id']}")
    print(f"Target Unit:  {res['target_symbol']} in {res['target_file']}")
    print(f"Commit SHA:   {res['commit_sha']}")

    print("\n2. Latency Telemetry Breakdown (Real Model Network Latency):")
    for k, v in res.get("latency_telemetry", {}).items():
        print(f"  {k}: {v} ms")

    print("\n3. Real Model Output:")
    w = res["worker_result"]
    print(f"Model: {w.get('model')}")
    print(f"Worker Latency: {w.get('worker_latency_ms')} ms")
    print("Generated Code:\n", w.get("generated_code"))

    print("\n4. Guardrail Evaluation:")
    g = res["guardrail"]
    print(f"Status:             {g['status']}")
    print(f"Syntax Valid:       {g['syntax_valid']}")
    print(f"Auto-Fix Attempted: {g['auto_fix_attempted']}")
    print(f"Rolled Back:        {g['rolled_back']}")

    print("\n" + "=" * 90)
    print("DEMO COMPLETE.")
    print("=" * 90)


if __name__ == "__main__":
    main()

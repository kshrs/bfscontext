"""
Tests for CapsuleMCPServer:
- Server startup & tool registration
- Valid delegation end-to-end
- Invalid target file handling
- Invalid repository handling
- Missing target symbol handling
- Path traversal security guardrail
- Mock worker integration & [MOCK / DEMO ONLY] label
- Stale intent detection through MCP
- Token metrics reporting
- Deterministic repeated invocation
- Traceable request_id propagation
- JSON-RPC protocol handling
"""

from pathlib import Path
import pytest

from capsulemcp.adapters.mock import MockIntentProvider, MockTelemetrySink, MockWorkerProvider
from capsulemcp.mcp_server import CapsuleMCPServer


@pytest.fixture
def sample_repo_path():
    return Path(__file__).parent.parent / "demo" / "sample_repo"


def test_mcp_server_startup_and_tool_registration(sample_repo_path):
    server = CapsuleMCPServer(repo_path=str(sample_repo_path))
    tools = server.get_tool_definitions()

    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == "delegate_with_capsule"
    assert "target_file" in tool["inputSchema"]["properties"]
    assert "subtask" in tool["inputSchema"]["properties"]
    assert "worker_model" in tool["inputSchema"]["properties"]
    assert "target_symbol" in tool["inputSchema"]["properties"]
    assert "target_file" in tool["inputSchema"]["required"]


def test_valid_delegation_flow(sample_repo_path):
    telemetry = MockTelemetrySink()
    worker = MockWorkerProvider()
    server = CapsuleMCPServer(
        repo_path=str(sample_repo_path),
        telemetry_sink=telemetry,
        worker_provider=worker,
    )

    custom_req_id = "req-test-12345"
    response = server.delegate_with_capsule(
        target_file="src/billing.py",
        subtask="Write test for charge_user",
        target_symbol="charge_user",
        request_id=custom_req_id,
    )

    assert response["status"] == "success"
    assert response["request_id"] == custom_req_id
    assert response["target_symbol"] == "charge_user"
    assert response["is_intent_stale"] is False
    assert len(response["commit_sha"]) == 40

    # Structured capsule prompt
    capsule_prompt = response["capsule_prompt"]
    assert "[TASK INSTRUCTIONS]" in capsule_prompt
    assert "[IMMUTABLE CODE CONTRACTS]" in capsule_prompt
    assert "def charge_user(" in capsule_prompt

    # Dependencies
    deps = response["dependencies"]
    dep_names = {d["name"] for d in deps}
    assert "PaymentError" in dep_names
    assert "DatabaseClient" in dep_names

    # Token metrics
    tm = response["token_metrics"]
    assert tm["capsule_tokens"] > 0
    assert tm["tokens_saved"] > 0

    # Worker output
    worker_res = response["worker_result"]
    assert worker_res["status"] == "success"
    assert worker_res["is_mock"] is True
    assert "MOCK / DEMO ONLY" in worker_res["disclaimer"]
    assert worker_res["request_id"] == custom_req_id

    # Telemetry
    assert len(telemetry.records) == 1
    assert telemetry.records[0]["metadata"]["request_id"] == custom_req_id


def test_invalid_target_file(sample_repo_path):
    server = CapsuleMCPServer(repo_path=str(sample_repo_path))
    res = server.delegate_with_capsule(
        target_file="src/non_existent.py",
        subtask="Do something",
    )
    assert res["status"] == "error"
    assert "Target file not found" in res["error"]
    assert res["error_type"] == "FileNotFoundError"


def test_invalid_repository():
    server = CapsuleMCPServer(repo_path="C:/non_existent_dir_12345")
    res = server.delegate_with_capsule(
        target_file="test.py",
        subtask="Do something",
        repo_path="C:/non_existent_dir_12345",
    )
    assert res["status"] == "error"
    assert "repository path does not exist" in res["error"]


def test_missing_target_symbol(sample_repo_path):
    server = CapsuleMCPServer(repo_path=str(sample_repo_path))
    res = server.delegate_with_capsule(
        target_file="src/billing.py",
        subtask="Do something",
        target_symbol="phantom_symbol_not_present",
    )
    assert res["status"] == "error"
    assert "phantom_symbol_not_present" in res["error"]
    assert res["error_type"] == "UnitNotFoundError"


def test_path_traversal_security_rejection(sample_repo_path):
    server = CapsuleMCPServer(repo_path=str(sample_repo_path))
    res = server.delegate_with_capsule(
        target_file="../../secret_keys.py",
        subtask="Steal secrets",
    )
    assert res["status"] == "error"
    assert "Security violation" in res["error"]
    assert res["error_type"] == "PermissionError"


def test_stale_intent_detection(sample_repo_path):
    stale_intent_provider = MockIntentProvider(
        default_intent="Stale migration",
        simulated_commit_sha="0000000000000000000000000000000000000001",
    )
    server = CapsuleMCPServer(
        repo_path=str(sample_repo_path),
        intent_provider=stale_intent_provider,
    )
    res = server.delegate_with_capsule(
        target_file="src/billing.py",
        subtask="Write test for charge_user",
        target_symbol="charge_user",
    )
    assert res["status"] == "success"
    assert res["is_intent_stale"] is True
    assert "[HISTORICAL: MAY BE DEPRECATED]" in res["capsule_prompt"]


def test_deterministic_repeated_invocation(sample_repo_path):
    server = CapsuleMCPServer(repo_path=str(sample_repo_path))
    res1 = server.delegate_with_capsule(
        target_file="src/billing.py",
        subtask="Write test for charge_user",
        target_symbol="charge_user",
    )
    res2 = server.delegate_with_capsule(
        target_file="src/billing.py",
        subtask="Write test for charge_user",
        target_symbol="charge_user",
    )
    assert res1["status"] == "success"
    assert res2["status"] == "success"
    assert res1["capsule_prompt"] == res2["capsule_prompt"]
    assert res1["token_metrics"] == res2["token_metrics"]


def test_json_rpc_tools_list_and_call(sample_repo_path):
    server = CapsuleMCPServer(repo_path=str(sample_repo_path))

    # tools/list
    list_rpc = server.handle_json_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert list_rpc["id"] == 1
    assert "tools" in list_rpc["result"]

    # tools/call
    call_rpc = server.handle_json_rpc({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "delegate_with_capsule",
            "arguments": {
                "target_file": "src/billing.py",
                "subtask": "Write test for charge_user",
                "target_symbol": "charge_user",
            },
        },
    })
    assert call_rpc["id"] == 2
    assert "result" in call_rpc
    assert call_rpc["result"]["structured_data"]["status"] == "success"

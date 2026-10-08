"""
CapsuleMCP Server: Exposes algorithmic context compilation and worker delegation via MCP.
Adheres to JSON-RPC 2.0 / MCP tool specifications.

Architecture:
    AGY / Main Agent
          |
          v
    MCP Server (delegate_with_capsule)
          |
          v
    Context Compiler
          |
          v
    Context Capsule
          |
          v
    Worker Provider (Mock / Pluggable)
          |
          v
    Telemetry Sink
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid

from capsulemcp.adapters.interfaces import CodeAnalyzer, FixerProvider, IntentProvider, TelemetrySink, WorkerProvider
from capsulemcp.adapters.mock.mock_intent import MockIntentProvider
from capsulemcp.adapters.mock.mock_telemetry import MockTelemetrySink
from capsulemcp.adapters.mock.mock_worker import MockWorkerProvider
from capsulemcp.adapters.real_worker import RealWorkerProvider
from capsulemcp.ast_extractor import ASTExtractor, UnitNotFoundError, UnsupportedLanguageError
from capsulemcp.circuit_breaker import CircuitBreaker, GuardrailResult, GuardrailStatus
from capsulemcp.context_compiler import ContextCompiler
from capsulemcp.models import ContextCapsule

logger = logging.getLogger(__name__)


@dataclass
class DelegationRequest:
    """Validated inputs for delegate_with_capsule tool."""
    target_file: str
    subtask: str
    intent: Optional[str] = None
    worker_model: str = "mock"
    target_symbol: Optional[str] = None
    max_dependency_depth: int = 1
    repo_path: str = "."
    apply_to_disk: bool = False
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class DelegationResponse:
    """Structured response returned by delegate_with_capsule."""
    status: str
    request_id: str
    target_file: str
    target_symbol: str
    commit_sha: str
    is_intent_stale: bool
    capsule_prompt: str
    token_metrics: Dict[str, Any]
    dependencies: List[Dict[str, Any]]
    worker_result: Dict[str, Any]
    guardrail: Dict[str, Any]
    compilation_trace: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "request_id": self.request_id,
            "target_file": self.target_file,
            "target_symbol": self.target_symbol,
            "commit_sha": self.commit_sha,
            "is_intent_stale": self.is_intent_stale,
            "capsule_prompt": self.capsule_prompt,
            "token_metrics": self.token_metrics,
            "dependencies": self.dependencies,
            "worker_result": self.worker_result,
            "guardrail": self.guardrail,
            "compilation_trace": self.compilation_trace,
            "error": self.error,
        }


class CapsuleMCPServer:
    """
    Thin Model Context Protocol (MCP) Server for CapsuleMCP.
    Provides tool registration, request validation, context compilation orchestration,
    worker dispatch, and one-strike circuit breaker enforcement.
    """

    TOOL_NAME = "delegate_with_capsule"

    def __init__(
        self,
        repo_path: str = ".",
        intent_provider: Optional[IntentProvider] = None,
        telemetry_sink: Optional[TelemetrySink] = None,
        worker_provider: Optional[WorkerProvider] = None,
        code_analyzer: Optional[CodeAnalyzer] = None,
        fixer: Optional[FixerProvider] = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.intent_provider = intent_provider or MockIntentProvider()
        self.telemetry_sink = telemetry_sink or MockTelemetrySink()
        self.worker_provider = worker_provider or MockWorkerProvider()
        self.code_analyzer = code_analyzer or ASTExtractor(repo_path=str(self.repo_path))
        self.guardrail = CircuitBreaker(repo_path=str(self.repo_path), fixer=fixer)

        self.compiler = ContextCompiler(
            repo_path=str(self.repo_path),
            intent_provider=self.intent_provider,
            telemetry_sink=self.telemetry_sink,
            code_analyzer=self.code_analyzer,
        )

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns standard MCP tool specifications."""
        return [
            {
                "name": self.TOOL_NAME,
                "description": (
                    "Algorithmically compiles the minimum sufficient context capsule for a subtask "
                    "and delegates execution to the worker model. Context is compiled, not summarized."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target_file": {
                            "type": "string",
                            "description": "Path to the target source file within repository.",
                        },
                        "subtask": {
                            "type": "string",
                            "description": "The specific delegated prompt or implementation instruction.",
                        },
                        "intent": {
                            "type": "string",
                            "description": "Optional architectural intent or PR description.",
                        },
                        "worker_model": {
                            "type": "string",
                            "description": "Target worker identifier or model adapter (default: 'mock').",
                            "default": "mock",
                        },
                        "target_symbol": {
                            "type": "string",
                            "description": "Optional explicit function, method, or class name to isolate.",
                        },
                        "max_dependency_depth": {
                            "type": "integer",
                            "description": "Maximum hops for bounded dependency traversal (0, 1, or 2).",
                            "default": 1,
                        },
                        "repo_path": {
                            "type": "string",
                            "description": "Repository root path (defaults to server repo_path).",
                        },
                        "apply_to_disk": {
                            "type": "boolean",
                            "description": "Whether to safely write validated output to disk (default: false).",
                            "default": False,
                        },
                    },
                    "required": ["target_file", "subtask"],
                },
            }
        ]

    def _validate_request(self, args: Dict[str, Any]) -> DelegationRequest:
        """
        Validates request parameters and guards against path traversal security attacks.
        """
        target_file = args.get("target_file")
        if not target_file or not isinstance(target_file, str):
            raise ValueError("Parameter 'target_file' must be a non-empty string.")

        subtask = args.get("subtask")
        if not subtask or not isinstance(subtask, str):
            raise ValueError("Parameter 'subtask' must be a non-empty string.")

        active_repo = Path(args.get("repo_path", self.repo_path)).resolve()
        if not active_repo.exists() or not active_repo.is_dir():
            raise FileNotFoundError(f"Configured repository path does not exist: {active_repo}")

        # Resolve target file path and prevent directory traversal outside allowed repo
        candidate_path = Path(target_file)
        if not candidate_path.is_absolute():
            resolved_target = (active_repo / candidate_path).resolve()
        else:
            resolved_target = candidate_path.resolve()

        try:
            resolved_target.relative_to(active_repo)
        except ValueError:
            raise PermissionError(
                f"Security violation: path traversal outside repository root is disallowed ({target_file})"
            )

        if not resolved_target.exists() or not resolved_target.is_file():
            raise FileNotFoundError(f"Target file not found in repository: {target_file}")

        if resolved_target.suffix != ".py":
            raise UnsupportedLanguageError(
                f"Target file language '{resolved_target.suffix}' is unsupported (expected .py)."
            )

        max_depth = args.get("max_dependency_depth", 1)
        try:
            max_depth = int(max_depth)
            if max_depth < 0:
                max_depth = 0
        except (ValueError, TypeError):
            max_depth = 1

        request_id = args.get("request_id") or str(uuid.uuid4())
        apply_to_disk = bool(args.get("apply_to_disk", False))

        return DelegationRequest(
            target_file=str(resolved_target.relative_to(active_repo)),
            subtask=subtask,
            intent=args.get("intent"),
            worker_model=str(args.get("worker_model", "mock")),
            target_symbol=args.get("target_symbol"),
            max_dependency_depth=max_depth,
            repo_path=str(active_repo),
            apply_to_disk=apply_to_disk,
            request_id=str(request_id),
        )

    def delegate_with_capsule(self, **kwargs) -> Dict[str, Any]:
        """
        Executes delegate_with_capsule tool call.
        Validates input, compiles ContextCapsule, delegates to WorkerProvider, and records telemetry.
        """
        t0 = time.perf_counter()
        request_id = kwargs.get("request_id") or str(uuid.uuid4())

        try:
            req = self._validate_request(kwargs)
            request_id = req.request_id

            # 1. Compile context capsule with traceable metadata
            t_comp_start = time.perf_counter()
            capsule = self.compiler.generate_context_capsule(
                file_path=req.target_file,
                subtask_description=req.subtask,
                intent_summary=req.intent,
                target_unit_name=req.target_symbol,
                repo_path=req.repo_path,
                dependency_depth=req.max_dependency_depth,
                metadata={
                    "request_id": request_id,
                    "worker_model": req.worker_model,
                    "caller": "CapsuleMCPServer",
                },
            )
            comp_latency_ms = (time.perf_counter() - t_comp_start) * 1000.0

            # 2. Select Worker Provider based on worker_model
            active_worker = self.worker_provider
            if req.worker_model not in ("mock", "mock-claude-worker") and not isinstance(self.worker_provider, RealWorkerProvider):
                # Dynamically instantiate RealWorkerProvider for requested real model if server default is mock
                active_worker = RealWorkerProvider(model=req.worker_model)

            # 3. Delegate to worker provider (sends ONLY the capsule)
            t_worker_start = time.perf_counter()
            worker_res = active_worker.generate(capsule)
            worker_lat_ms = (time.perf_counter() - t_worker_start) * 1000.0
            worker_res["worker_latency_ms"] = round(worker_lat_ms, 2)
            worker_res["request_id"] = request_id

            # 4. Pass worker output through One-Strike Guardrail / Circuit Breaker
            t_guard_start = time.perf_counter()
            generated_code = worker_res.get("generated_code", "")
            guardrail_res = self.guardrail.evaluate_and_guard(
                worker_code=generated_code,
                target_file=req.target_file,
                target_symbol=req.target_symbol,
                commit_sha=capsule.git_head_sha,
                apply_to_disk=req.apply_to_disk,
            )
            guard_latency_ms = (time.perf_counter() - t_guard_start) * 1000.0
            total_latency_ms = (time.perf_counter() - t0) * 1000.0

            # 5. Record extended latency telemetry
            latency_breakdown = {
                "compilation_latency_ms": round(comp_latency_ms, 2),
                "worker_latency_ms": round(worker_lat_ms, 2),
                "guardrail_latency_ms": round(guard_latency_ms, 2),
                "total_request_latency_ms": round(total_latency_ms, 2),
            }

            dep_info = [
                {
                    "name": d.name,
                    "file": d.file_path,
                    "type": d.unit_type,
                    "is_direct": d.is_direct,
                }
                for d in capsule.dependencies
            ]

            metrics_dict = capsule.token_metrics.to_dict() if capsule.token_metrics else {}

            # Overall status reflects guardrail outcome
            overall_status = "success" if guardrail_res.status in (GuardrailStatus.SUCCESS, GuardrailStatus.REPAIRED) else "failed"

            resp = DelegationResponse(
                status=overall_status,
                request_id=request_id,
                target_file=capsule.target_file_path,
                target_symbol=capsule.target_unit.name,
                commit_sha=capsule.git_head_sha,
                is_intent_stale=capsule.intent_context.is_stale,
                capsule_prompt=capsule.render(),
                token_metrics=metrics_dict,
                dependencies=dep_info,
                worker_result=worker_res,
                guardrail=guardrail_res.to_dict(),
                compilation_trace=capsule.compilation_trace,
            )
            resp_dict = resp.to_dict()
            resp_dict["latency_telemetry"] = latency_breakdown
            return resp_dict

        except Exception as e:
            logger.warning("Delegation error in MCP server: %s", e)
            return {
                "status": "error",
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def handle_json_rpc(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handles standard JSON-RPC / MCP tool calls."""
        req_id = request_payload.get("id")
        method = request_payload.get("method")
        params = request_payload.get("params", {})

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.get_tool_definitions()},
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            if tool_name == self.TOOL_NAME:
                result = self.delegate_with_capsule(**args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2),
                            }
                        ],
                        "structured_data": result,
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method/Tool '{tool_name}' not found"},
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": f"Unsupported method: {method}"},
            }

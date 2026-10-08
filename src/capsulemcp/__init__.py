"""
CapsuleMCP — Algorithmic Context Compilation for Multi-Agent AI.
"""

from capsulemcp.adapters.real_worker import RealWorkerProvider
from capsulemcp.circuit_breaker import CircuitBreaker, GuardrailResult, GuardrailStatus
from capsulemcp.context_compiler import ContextCompiler, generate_context_capsule
from capsulemcp.mcp_server import CapsuleMCPServer
from capsulemcp.telemetry import log_delegation_metrics

__version__ = "0.1.0"
__all__ = [
    "CapsuleMCPServer",
    "CircuitBreaker",
    "ContextCompiler",
    "GuardrailResult",
    "GuardrailStatus",
    "RealWorkerProvider",
    "generate_context_capsule",
    "log_delegation_metrics",
]


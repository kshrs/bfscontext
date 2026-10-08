"""
CapsuleMCP — Algorithmic Context Compilation for Multi-Agent AI.
"""

from capsulemcp.context_compiler import ContextCompiler, generate_context_capsule
from capsulemcp.mcp_server import CapsuleMCPServer

__version__ = "0.1.0"
__all__ = ["CapsuleMCPServer", "ContextCompiler", "generate_context_capsule"]

"""
Adapter interfaces and mock implementations.
"""

from capsulemcp.adapters.interfaces import IntentProvider, TelemetrySink, WorkerProvider

__all__ = ["IntentProvider", "WorkerProvider", "TelemetrySink"]

"""
network.py — Compatibility wrapper for Blueprint V1.4 spec.
The actual implementation lives in graph_builder.py.
"""
from src.bloque1.graph_builder import build_directed_graph, EdgePayload

__all__ = ["build_directed_graph", "EdgePayload"]

# src/bloque4/utils.py
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Sequence

from .schema import Graph, Edge


def infer_edge_ids_from_path(graph: Graph, node_path: Sequence[str]) -> List[str]:
    """Inferir edge_ids por pares consecutivos de nodos; devuelve lista de edge_id."""
    edge_ids: List[str] = []
    if not node_path:
        return edge_ids
    for a, b in zip(node_path, node_path[1:]):
        found = None
        for e in graph.edges:
            if e.source == a and e.target == b:
                found = e.edge_id
                break
        if found is not None:
            edge_ids.append(found)
    return edge_ids


def normalize_solution(sol: Any, graph: Graph, ordered_edges: Sequence[Edge]) -> SimpleNamespace:
    """
    Normaliza la salida del engine a un objeto con atributos mínimos esperados:
      path, edges, total_cost, optimized_cost, total_time, total_risk

    Acepta:
      - list (node path)
      - dict
      - objeto con atributos (SimpleNamespace, dataclass, etc.)
    """
    # Caso lista de nodos
    if isinstance(sol, list):
        path = [str(x) for x in sol]
        edges = infer_edge_ids_from_path(graph, path)
        if edges:
            total_cost = sum(float(graph.edge_by_id(eid).cost) for eid in edges)
            total_risk = sum(float(graph.edge_by_id(eid).risk or 0.0) for eid in edges)
        else:
            total_cost = float(sum(getattr(e, "cost", 0.0) for e in ordered_edges))
            total_risk = float(sum(getattr(e, "risk", 0.0) for e in ordered_edges))
        return SimpleNamespace(
            path=path,
            edges=edges,
            total_cost=float(total_cost),
            optimized_cost=float(total_cost),
            total_time=0.0,
            total_risk=float(total_risk)
        )

    # Caso dict-like
    if isinstance(sol, dict):
        path = list(sol.get("path") or sol.get("nodes") or sol.get("node_path") or [])
        edges = list(sol.get("edges") or sol.get("arc_path") or infer_edge_ids_from_path(graph, path))
        total_cost = float(sol.get("total_cost", 0.0) or 0.0)
        optimized_cost = float(sol.get("optimized_cost", total_cost) or total_cost)
        total_time = float(sol.get("total_time", 0.0) or 0.0)
        total_risk = float(sol.get("total_risk", 0.0) or 0.0)
        return SimpleNamespace(
            path=path,
            edges=edges,
            total_cost=total_cost,
            optimized_cost=optimized_cost,
            total_time=total_time,
            total_risk=total_risk
        )

    # Caso objeto con atributos
    sol_obj = sol
    path = list(getattr(sol_obj, "path", []) or [])
    edges = list(getattr(sol_obj, "edges", []) or infer_edge_ids_from_path(graph, path))
    total_cost = float(getattr(sol_obj, "total_cost", 0.0) or 0.0)
    optimized_cost = float(getattr(sol_obj, "optimized_cost", total_cost) or total_cost)
    total_time = float(getattr(sol_obj, "total_time", 0.0) or 0.0)
    total_risk = float(getattr(sol_obj, "total_risk", 0.0) or 0.0)

    return SimpleNamespace(
        path=path,
        edges=edges,
        total_cost=total_cost,
        optimized_cost=optimized_cost,
        total_time=total_time,
        total_risk=total_risk
    )

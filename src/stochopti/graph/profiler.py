"""stochopti/graph/profiler.py — Analizador Estructural de Grafos."""

import logging
import numpy as np
from typing import Dict, List, Tuple, Any

from stochopti.core.types import GraphSpec, PathSolution
from stochopti.pareto.solution import RouteProfile

LOGGER = logging.getLogger(__name__)

def profile_route(
    graph: GraphSpec, 
    solution: PathSolution, 
    rigidity_weights: Tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)
) -> RouteProfile:
    """Analiza métricas estructurales de una solución (Entropía, Redundancia, Rigidez)."""
    edge_ids = solution.edges
    if not edge_ids:
        return RouteProfile(0.0, 0.0, 0.0, 0.0, {})

    edges_in_route = []
    for eid in edge_ids:
        e = next((edge for edge in graph.edges if edge.edge_id == eid), None)
        if e is not None:
            edges_in_route.append(e)

    risk_weights_list = []
    for e in edges_in_route:
        # Busca risk_weight si existe para compatibilidad
        rw = e.objectives.get("risk_weight", 0.0)
        risk_weights_list.append(float(rw))

    risk_weights = np.array(risk_weights_list, dtype=float)

    scale = len(edge_ids) / max(1, len(graph.edges))
    entropy = _calculate_relative_entropy(risk_weights)
    ri = _calculate_real_redundancy(graph, edge_ids, threshold=1.3)
    rigidity, sensitivity = _calculate_rigidity(graph, edges_in_route, ri, rigidity_weights)

    return RouteProfile(
        risk_scale=float(np.sum(risk_weights)),
        entropy=entropy,
        rigidity=rigidity,
        redundancy_index=ri,
        sensitivity_vector={
            "scale": float(scale),
            **sensitivity
        }
    )

def _calculate_relative_entropy(weights: np.ndarray) -> float:
    """Mide la concentración (entropía de Shannon normalizada)."""
    if weights.size <= 1 or np.sum(weights) <= 0:
        return 0.0
    p = weights / np.sum(weights)
    p = p[p > 0]
    if p.size == 0:
        return 0.0
    h_abs = -float(np.sum(p * np.log2(p)))
    h_max = float(np.log2(weights.size)) if weights.size > 1 else 1.0
    return float(h_abs / h_max)

def _calculate_real_redundancy(graph: GraphSpec, path_edge_ids: List[str], threshold: float) -> float:
    """Índice de redundancia: arcos con alternativa viable."""
    if not path_edge_ids:
        return 0.0
    redundant_count = 0
    for edge_id in path_edge_ids:
        edge = next((e for e in graph.edges if e.edge_id == edge_id), None)
        if edge is None:
            continue
        alternatives = [
            e for e in graph.edges
            if e.source == edge.source and e.target == edge.target and e.edge_id != edge.edge_id
        ]
        if alternatives:
            if any(alt.objectives.get("cost", 0) <= edge.objectives.get("cost", 0) * threshold for alt in alternatives):
                redundant_count += 1
    return redundant_count / len(path_edge_ids)

def _calculate_rigidity(
    graph: GraphSpec,
    edges_in_route: List[Any],
    ri: float,
    rigidity_weights: Tuple[float, float, float, float]
) -> Tuple[float, Dict[str, float]]:
    """Calcula rigidez como combinación lineal de vulnerabilidades."""
    max_risk_edge = max((e.objectives.get("risk", 0.0) for e in edges_in_route), default=0.0)
    
    node_path = []
    for e in edges_in_route:
        node_path.append(e.source)
    if edges_in_route:
        node_path.append(edges_in_route[-1].target)

    node_exposure = 1.0 - (len(set(node_path)) / max(1, len(graph.nodes)))

    costs = np.array([float(e.objectives.get("cost", 0.0)) for e in edges_in_route], dtype=float)
    mean_cost = float(np.mean(costs)) if costs.size > 0 else 0.0
    cost_volatility = float(np.std(costs) / mean_cost) if mean_cost > 0 else 0.0
    cost_volatility = float(np.clip(cost_volatility, 0.0, 1.0))

    vulnerability = float(max(0.0, 1.0 - ri))

    components = {
        "edge_risk_impact": float(max_risk_edge),
        "node_exposure": float(node_exposure),
        "cost_volatility": cost_volatility,
        "redundancy_vulnerability": vulnerability
    }

    w_arr = np.array(list(rigidity_weights)[:4], dtype=float)
    if np.sum(w_arr) == 0:
        w_arr = np.array([0.25, 0.25, 0.25, 0.25], dtype=float)
    w_arr = w_arr / float(np.sum(w_arr))

    val_array = np.array([
        components["edge_risk_impact"],
        components["node_exposure"],
        components["cost_volatility"],
        components["redundancy_vulnerability"]
    ], dtype=float)

    rigidity = float(np.dot(w_arr, val_array))
    return rigidity, components

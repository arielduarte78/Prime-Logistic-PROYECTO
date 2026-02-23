from __future__ import annotations

from typing import Dict, Tuple
import logging

import numpy as np

from .schema import Graph, OptimizerConfig, RawSolution, RouteProfile

LOGGER = logging.getLogger(__name__)


def profile_route(
    graph: Graph,
    solution: RawSolution,
    config: OptimizerConfig,
) -> RouteProfile:
    """
    Analizador estructural de rutas.
    Transforma una solución cruda en un RouteProfile robusto y determinista.
    """
    # Ruta vacía -> perfil neutro
    if not solution.edges:
        return RouteProfile(0.0, 0.0, 1.0, 0.0, {})

    # 1. Preparación de datos vectoriales (defensivo)
    try:
        edges_in_route = [graph.edge_by_id(eid) for eid in solution.edges]
    except KeyError as exc:
        LOGGER.error("Edge id no encontrado en graph.edge_indexer: %s", exc)
        raise

    # Extraemos risk_weight como floats; filtramos None
    risk_weights_list = [float(e.risk_weight) for e in edges_in_route if e.risk_weight is not None]
    if risk_weights_list:
        risk_weights = np.array(risk_weights_list, dtype=float)
    else:
        risk_weights = np.array([], dtype=float)

    # 2. Cálculo de métricas base
    scale = len(solution.edges) / max(1, len(graph.edges))
    entropy = _calculate_relative_entropy(risk_weights)

    # 3. Redundancia Real (Análisis de Grafo, no de lista)
    ri = _calculate_real_redundancy(graph, solution, threshold=1.3)

    # 4. Rigidez (Sensibilidad al fallo crítico)
    rigidity, sensitivity = _calculate_rigidity(graph, solution, config, ri)

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
    """Mide la concentración del riesgo (entropía de Shannon normalizada)."""
    if weights.size <= 1 or np.sum(weights) <= 0:
        return 0.0

    p = weights / np.sum(weights)
    p = p[p > 0]
    if p.size == 0:
        return 0.0

    h_abs = -float(np.sum(p * np.log2(p)))
    h_max = float(np.log2(weights.size)) if weights.size > 1 else 1.0
    return float(h_abs / h_max)


def _calculate_real_redundancy(graph: Graph, solution: RawSolution, threshold: float) -> float:
    """
    Calcula el índice de redundancia estructural.
    RI = (Arcos con alternativa viable) / (Total arcos de la ruta)
    """
    if not solution.edges:
        return 0.0

    redundant_count = 0
    for edge_id in solution.edges:
        edge = graph.edge_by_id(edge_id)
        alternatives = [
            e for e in graph.edges
            if e.source == edge.source and e.target == edge.target and e.edge_id != edge.edge_id
        ]

        if alternatives:
            if any((alt.cost is not None and alt.cost <= edge.cost * threshold) for alt in alternatives):
                redundant_count += 1

    return redundant_count / len(solution.edges)


def _calculate_rigidity(
    graph: Graph,
    solution: RawSolution,
    config: OptimizerConfig,
    ri: float
) -> Tuple[float, Dict[str, float]]:
    """
    Calcula la rigidez como combinación lineal de componentes de vulnerabilidad.
    Devuelve (rigidity, components_dict).
    """
    edges_in_route = [graph.edge_by_id(eid) for eid in solution.edges]

    # Edge risk impact
    max_risk_edge = max((e.risk or 0.0) for e in edges_in_route) if edges_in_route else 0.0

    # Node exposure: inverso de la diversidad de nodos en la ruta
    node_exposure = 1.0 - (len(set(solution.path)) / max(1, len(graph.nodes)))

    # Cost volatility (defensivo)
    costs = np.array([float(e.cost) for e in edges_in_route], dtype=float) if edges_in_route else np.array([0.0])
    mean_cost = float(np.mean(costs)) if costs.size > 0 else 0.0
    cost_volatility = float(np.std(costs) / mean_cost) if mean_cost > 0 else 0.0
    cost_volatility = float(np.clip(cost_volatility, 0.0, 1.0))

    # Redundancy vulnerability
    vulnerability = float(max(0.0, 1.0 - ri))

    components = {
        "edge_risk_impact": float(max_risk_edge),
        "node_exposure": float(node_exposure),
        "cost_volatility": cost_volatility,
        "redundancy_vulnerability": vulnerability
    }

    # Validar y normalizar weights de config.rigidity_weights
    weights = list(getattr(config, "rigidity_weights", (0.25, 0.25, 0.25, 0.25)))
    if len(weights) != 4:
        LOGGER.warning("rigidity_weights no tiene 4 elementos; normalizando.")
        # rellenar o truncar a 4 y normalizar
        while len(weights) < 4:
            weights.append(0.0)
        weights = weights[:4]
    w_arr = np.array(weights, dtype=float)
    # Normalizar si la suma es 0
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

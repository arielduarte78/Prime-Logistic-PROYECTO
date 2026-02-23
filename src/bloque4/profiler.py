from __future__ import annotations

from typing import Dict, Tuple, List
import logging

import numpy as np

from .schema import Graph, OptimizerConfig, RawSolution, RouteProfile

LOGGER = logging.getLogger(__name__)


def _find_edge_id_between(graph: Graph, u: str, v: str) -> str | None:
    """
    Busca el primer edge_id que conecta u -> v. Retorna None si no encuentra.
    """
    for e in graph.edges:
        if e.source == u and e.target == v:
            return e.edge_id
    return None


def _extract_edge_ids_from_solution(graph: Graph, solution: RawSolution) -> List[str]:
    """
    Extrae una lista de edge_ids desde la solución en varios formatos:
    - objeto con .edges
    - dict con 'edges' o 'arc_path'
    - objeto/dict con 'path' (lista de nodos): se infiere arcos por pares consecutivos
    - lista simple: se interpreta como path de nodos y se infieren arcos
    """
    # 1) Si tiene atributo edges y no está vacío, usarlo
    if hasattr(solution, "edges") and solution.edges:
        return list(solution.edges)

    # 2) Si es dict-like con 'edges' o 'arc_path'
    if isinstance(solution, dict):
        if "edges" in solution and solution["edges"]:
            return list(solution["edges"])
        if "arc_path" in solution and solution["arc_path"]:
            return list(solution["arc_path"])

    # 3) Si tiene path (lista de nodos) o es una lista (path de nodos)
    path = None
    if hasattr(solution, "path"):
        path = list(getattr(solution, "path") or [])
    elif isinstance(solution, dict):
        path = list(solution.get("path") or solution.get("nodes") or [])
    elif isinstance(solution, list):
        path = list(solution)

    if path:
        edge_ids: List[str] = []
        for a, b in zip(path, path[1:]):
            eid = _find_edge_id_between(graph, a, b)
            if eid is not None:
                edge_ids.append(eid)
            else:
                LOGGER.debug("No se encontró arco directo %s -> %s al inferir edges desde path.", a, b)
        return edge_ids

    # 4) Nada encontrado: retornar lista vacía
    return []


def profile_route(
    graph: Graph,
    solution: RawSolution,
    config: OptimizerConfig,
) -> RouteProfile:
    """
    Analizador estructural de rutas.
    Transforma una solución cruda en un RouteProfile robusto y determinista.
    Acepta soluciones en varios formatos (objeto, dict, lista) y las normaliza.
    """
    # Normalizar y extraer edge ids
    try:
        edge_ids = _extract_edge_ids_from_solution(graph, solution)
    except Exception as exc:
        LOGGER.exception("Error extrayendo arcos de la solución: %s", exc)
        edge_ids = []

    # Ruta vacía -> perfil neutro
    if not edge_ids:
        return RouteProfile(0.0, 0.0, 0.0, 0.0, {})

    # 1. Preparación de datos vectoriales (defensivo)
    edges_in_route = []
    for eid in edge_ids:
        try:
            e = graph.edge_by_id(eid)
        except Exception:
            # Fallback: buscar en la lista de edges por edge_id
            e = next((edge for edge in graph.edges if edge.edge_id == eid), None)
            if e is None:
                LOGGER.error("Edge id no encontrado en graph: %s", eid)
                raise KeyError(eid)
        edges_in_route.append(e)

    # Extraemos risk_weight como floats; filtramos None
    risk_weights_list = []
    for e in edges_in_route:
        try:
            if getattr(e, "risk_weight", None) is not None:
                risk_weights_list.append(float(e.risk_weight))
        except Exception:
            LOGGER.debug("No se pudo leer risk_weight para edge %s", getattr(e, "edge_id", "<unknown>"))

    if risk_weights_list:
        risk_weights = np.array(risk_weights_list, dtype=float)
    else:
        risk_weights = np.array([], dtype=float)

    # 2. Cálculo de métricas base
    scale = len(edge_ids) / max(1, len(graph.edges))
    entropy = _calculate_relative_entropy(risk_weights)

    # 3. Redundancia Real (Análisis de Grafo, no de lista)
    ri = _calculate_real_redundancy(graph, edge_ids, threshold=1.3)

    # 4. Rigidez (Sensibilidad al fallo crítico)
    rigidity, sensitivity = _calculate_rigidity(graph, edge_ids, config, ri)

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


def _calculate_real_redundancy(graph: Graph, path_edge_ids: List[str], threshold: float) -> float:
    """
    Calcula el índice de redundancia estructural.
    RI = (Arcos con alternativa viable) / (Total arcos de la ruta)
    """
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
            if any((alt.cost is not None and alt.cost <= edge.cost * threshold) for alt in alternatives):
                redundant_count += 1

    return redundant_count / len(path_edge_ids)


def _calculate_rigidity(
    graph: Graph,
    path_edge_ids: List[str],
    config: OptimizerConfig,
    ri: float
) -> Tuple[float, Dict[str, float]]:
    """
    Calcula la rigidez como combinación lineal de componentes de vulnerabilidad.
    Devuelve (rigidity, components_dict).
    """
    edges_in_route = [next((e for e in graph.edges if e.edge_id == eid), None) for eid in path_edge_ids]
    edges_in_route = [e for e in edges_in_route if e is not None]

    # Edge risk impact
    max_risk_edge = max((getattr(e, "risk", 0.0) or 0.0) for e in edges_in_route) if edges_in_route else 0.0

    # Node exposure: inverso de la diversidad de nodos en la ruta
    # Intentamos reconstruir path de nodos a partir de edges si no hay path en solution
    node_path = []
    for e in edges_in_route:
        node_path.append(e.source)
    if edges_in_route:
        node_path.append(edges_in_route[-1].target)

    node_exposure = 1.0 - (len(set(node_path)) / max(1, len(graph.nodes)))

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

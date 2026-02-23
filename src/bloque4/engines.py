from __future__ import annotations

import logging
from dataclasses import replace
from typing import Dict, List, Tuple

import numpy as np
from types import MappingProxyType

from .schema import Edge, Graph, OptimizerConfig, RawSolution, FailureAssumption

LOGGER = logging.getLogger(__name__)
CLAMP_EPSILON = 1e-7
PROBABILITY_EPSILON = 1e-9
LOG_EPSILON = 1e-9
_RISK_TRANSFORM_VALIDATED = False


class OptimizationEngine:
    def solve(self, graph: Graph, phi_vector: np.ndarray, config: OptimizerConfig) -> RawSolution:
        raise NotImplementedError


def _clamp_phi(phi_vector: np.ndarray) -> Tuple[np.ndarray, bool]:
    phi = np.asarray(phi_vector, dtype=float)
    clamped = np.clip(phi, 0.0, 1.0 - CLAMP_EPSILON)
    did_clamp = not np.allclose(phi, clamped, atol=PROBABILITY_EPSILON)
    return clamped, did_clamp


def _risk_weights(phi_vector: np.ndarray) -> np.ndarray:
    return -np.log1p(-phi_vector)


def _cap_risk_weights(risk_weights: np.ndarray, max_risk_weight: float) -> Tuple[np.ndarray, bool]:
    capped = np.minimum(risk_weights, max_risk_weight)
    did_cap = not np.allclose(risk_weights, capped, atol=PROBABILITY_EPSILON)
    return capped, did_cap


def _apply_risk_to_graph(
    graph: Graph, phi_vector: np.ndarray, config: OptimizerConfig
) -> Tuple[Graph, np.ndarray, np.ndarray]:
    if config.strict_probabilities:
        clamped_phi = np.asarray(phi_vector, dtype=float)
    else:
        clamped_phi, did_clamp = _clamp_phi(phi_vector)
        if did_clamp:
            LOGGER.warning("Phi vector clamped to [0, 1 - 1e-7] for stability.")
    risk_weights = _risk_weights(clamped_phi)
    risk_weights, did_cap = _cap_risk_weights(risk_weights, config.max_risk_weight)
    if did_cap:
        LOGGER.warning("Risk weights capped at max_risk_weight=%s.", config.max_risk_weight)

    updated_edges: List[Edge] = []
    for edge in graph.edges:
        index = graph.edge_indexer[edge.edge_id]
        risk = float(clamped_phi[index])
        risk_weight = float(risk_weights[index])
        updated_edges.append(
            replace(
                edge,
                risk=risk,
                risk_weight=risk_weight,
            )
        )

    return (
        Graph(
            nodes=graph.nodes,
            edges=updated_edges,
            edge_indexer=MappingProxyType(dict(graph.edge_indexer)),
        ),
        risk_weights,
        clamped_phi,
    )


class DijkstraEngine(OptimizationEngine):
    """
    Compatibility wrapper for legacy code that may still instantiate DijkstraEngine
    with keyword arguments. The scalar Dijkstra solver was removed; solve still
    raises NotImplementedError to direct users to the multiobjective engine.
    """
    def __init__(self, *args, **kwargs):
        # Accept arbitrary kwargs for backward compatibility (eps_1, eps_2, etc.)
        # Store them for debugging if needed.
        self._init_kwargs = kwargs

    def solve(self, graph: Graph, phi_vector: np.ndarray, config: OptimizerConfig) -> RawSolution:
        raise NotImplementedError(
            "Scalar Dijkstra engine removed. Use src.bloque4.multiobjective_engine.MultiObjectiveEngine."
        )


class AStarEngine(OptimizationEngine):
    def solve(self, graph: Graph, phi_vector: np.ndarray, config: OptimizerConfig) -> RawSolution:
        raise NotImplementedError("AStarEngine requires heuristic implementation.")


class TabuSearchEngine(OptimizationEngine):
    def solve(self, graph: Graph, phi_vector: np.ndarray, config: OptimizerConfig) -> RawSolution:
        raise NotImplementedError("TabuSearchEngine not implemented.")


class SimulatedAnnealingEngine(OptimizationEngine):
    def solve(self, graph: Graph, phi_vector: np.ndarray, config: OptimizerConfig) -> RawSolution:
        raise NotImplementedError("SimulatedAnnealingEngine not implemented.")


class GeneticEngine(OptimizationEngine):
    def solve(self, graph: Graph, phi_vector: np.ndarray, config: OptimizerConfig) -> RawSolution:
        raise NotImplementedError("GeneticEngine not implemented.")


def _validate_phi_vector(graph: Graph, phi_vector: np.ndarray, config: OptimizerConfig) -> None:
    if len(phi_vector) != len(graph.edges):
        raise ValueError(
            f"Phi vector size ({len(phi_vector)}) does not match number of edges ({len(graph.edges)})."
        )
    if config.strict_probabilities:
        if np.any(phi_vector < 0) or np.any(phi_vector > 1):
            raise ValueError("Phi vector must contain probabilities in [0,1].")
        # Prevent log(0) later by rejecting exactly 1.0
        if np.any(phi_vector >= 1.0):
            raise ValueError("strict_probabilities=True but phi_vector contains 1.0; would cause log(0).")
    else:
        if np.any(phi_vector < -PROBABILITY_EPSILON) or np.any(phi_vector > 1 + PROBABILITY_EPSILON):
            raise ValueError("Phi vector must contain probabilities in [0,1].")


def _validate_edge_indexer(graph: Graph) -> None:
    if len(graph.edge_indexer) != len(graph.edges):
        raise ValueError("Edge indexer size mismatch.")

    max_index = len(graph.edges) - 1
    for edge in graph.edges:
        if edge.edge_id not in graph.edge_indexer:
            raise ValueError(f"Edge {edge.edge_id} missing in indexer.")

        idx = graph.edge_indexer[edge.edge_id]
        if not 0 <= idx <= max_index:
            raise ValueError(f"Edge index {idx} out of range for edge {edge.edge_id}.")

    if len(set(graph.edge_indexer.values())) != len(graph.edges):
        raise ValueError("Edge indexer contains duplicate indices.")


def _get_terminals(graph: Graph, config: OptimizerConfig) -> Tuple[str, str]:
    node_ids = {node.node_id for node in graph.nodes}
    if config.source_node_id not in node_ids:
        raise ValueError(f"Source node {config.source_node_id} not found in graph.")
    if config.target_node_id not in node_ids:
        raise ValueError(f"Target node {config.target_node_id} not found in graph.")
    return config.source_node_id, config.target_node_id


def _validate_graph_connectivity(graph: Graph, config: OptimizerConfig) -> None:
    """Reachability validation assumes directed edges; revisit for undirected models."""
    outgoing = {edge.source for edge in graph.edges}
    nodes = {node.node_id for node in graph.nodes}
    isolated = nodes - outgoing
    if isolated:
        LOGGER.warning("Nodes without outgoing edges detected: %s", sorted(isolated))

    source = config.source_node_id
    adjacency: Dict[str, List[str]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.source, []).append(edge.target)

    visited = set()
    stack = [source]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, []))

    unreachable = nodes - visited
    if unreachable:
        message = f"Nodes unreachable from source {source}: {sorted(unreachable)}"
        if config.require_full_connectivity:
            raise ValueError(message)
        LOGGER.warning(message)

    if config.target_node_id not in visited:
        raise ValueError(f"Target node {config.target_node_id} is unreachable from source {source}.")


def _validate_nonnegative_weights(graph: Graph, config: OptimizerConfig) -> None:
    for edge in graph.edges:
        if edge.cost < 0:
            raise ValueError(f"Edge cost must be non-negative: {edge.edge_id}.")


def _validate_risk_model_config(config: OptimizerConfig) -> None:
    # Keep only supported failure assumptions; future multiobjective engine may extend this.
    if config.failure_assumption == FailureAssumption.INDEPENDENT:
        return
    raise NotImplementedError(f"Failure assumption '{config.failure_assumption}' is not implemented.")


def _validate_risk_aggregation(phi_vector: np.ndarray, risk_weights: np.ndarray) -> None:
    if phi_vector.size == 0:
        return
    log_failure_product = float(np.sum(np.log1p(-phi_vector), dtype=np.float64))
    log_from_weights = -float(risk_weights.sum())
    if not np.isclose(log_failure_product, log_from_weights, atol=LOG_EPSILON):
        raise ValueError(
            "Risk aggregation invariant violated: "
            f"log_product={log_failure_product} log_from_weights={log_from_weights}."
        )


def _validate_path_risk_aggregation(
    path_edges: List[str],
    graph: Graph,
    phi_vector: np.ndarray,
    total_risk: float,
) -> None:
    if not path_edges:
        return
    indices = [graph.edge_indexer[edge_id] for edge_id in path_edges]
    path_phi = phi_vector[indices]
    log_failure_product = float(np.sum(np.log1p(-path_phi), dtype=np.float64))
    log_from_weights = -float(total_risk)
    if not np.isclose(log_failure_product, log_from_weights, atol=LOG_EPSILON):
        raise ValueError(
            "Path risk aggregation invariant violated: "
            f"log_product={log_failure_product} log_from_weights={log_from_weights}."
        )


def _validate_risk_transform() -> None:
    global _RISK_TRANSFORM_VALIDATED
    if _RISK_TRANSFORM_VALIDATED:
        return
    grid = np.linspace(0.0, 1.0 - CLAMP_EPSILON, num=256)
    weights = _risk_weights(grid)
    if np.any(np.diff(weights) < -PROBABILITY_EPSILON):
        raise ValueError("Risk weight transformation must be monotonic over [0, 1).")
    _RISK_TRANSFORM_VALIDATED = True


# NOTE
# Keep this module focused on risk transform and validation helpers only.
# Multiobjective routing is implemented in src/bloque4/multiobjective_engine.py.
# The DijkstraEngine class accepts arbitrary kwargs for backward compatibility
# but its solve method intentionally raises NotImplementedError.

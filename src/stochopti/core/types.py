"""stochopti/core/types.py — Tipos agnósticos fundamentales para la librería de optimización."""

from dataclasses import dataclass, field
from typing import Any, Tuple, List, Dict, Sequence

@dataclass(frozen=True)
class NodeSpec:
    """Nodo genérico en el grafo de optimización."""
    node_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class EdgeSpec:
    """Arista genérica con N dimensiones de costo."""
    edge_id: str
    source: str
    target: str
    objectives: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class GraphSpec:
    """Grafo genérico para el motor de optimización."""
    nodes: List[NodeSpec]
    edges: List[EdgeSpec]
    objective_names: Tuple[str, ...]

@dataclass(frozen=True)
class PathSolution:
    """Solución de camino encontrada por el motor."""
    path: List[str]
    edges: List[str]
    objective_values: Dict[str, float]

@dataclass(frozen=True)
class BetaPrior:
    """Parámetros de una distribución Beta (usada por motores bayesianos)."""
    alpha: float
    beta: float

    @property
    def mean(self) -> float:
        d = self.alpha + self.beta
        return self.alpha / d if d > 0 else 0.0

    @property
    def variance(self) -> float:
        a, b = self.alpha, self.beta
        d = (a + b) ** 2 * (a + b + 1)
        return (a * b) / d if d > 0 else 0.0

@dataclass(frozen=True)
class ConstrainedSolution:
    """Solution found under epsilon constraints."""
    path_edges: Tuple[str, ...]  # Canonical sequence of edge_ids
    objective_values: Tuple[float, ...]

def canonical_route_key(edge_ids_in_path_order: Sequence[str]) -> Tuple[str, ...]:
    """
    Returns an immutable canonical key for a route respecting topological order.
    Essential for supporting multigraphs with parallel edges.
    """
    return tuple(edge_ids_in_path_order)

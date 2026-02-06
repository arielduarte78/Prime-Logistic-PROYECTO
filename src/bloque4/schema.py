from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set
from enum import Enum

# Logging para advertencias de diseño
LOGGER = logging.getLogger(__name__)

# Enums
class StrategicTag(str, Enum):
    LOW_COST = "Eficiencia Quirúrgica (Low Cost)"
    HIGH_RESILIENCE = "Estructura Robusta (High Resilience)"
    DISTRIBUTED_RISK = "Resiliencia Distribuida (High Entropy)"
    BALANCED = "Balance Operativo"
    SUBOPTIMAL = "Eficiencia Subóptima"

class FailureAssumption(str, Enum):
    INDEPENDENT = "independent"

# Dataclasses
@dataclass
class RouteProfile:
    risk_scale: float = 0.0
    entropy: float = 0.0
    rigidity: float = 0.0
    redundancy_index: float = 0.0
    sensitivity_vector: "Dict[str, float]" = field(default_factory=dict)

@dataclass(frozen=True)
class Node:
    node_id: str

@dataclass(frozen=True)
class Edge:
    edge_id: str
    source: str
    target: str
    cost: float
    time: float = 0.0
    capacity: Optional[float] = None
    risk: Optional[float] = None
    risk_weight: Optional[float] = None

    def __post_init__(self) -> None:
        if self.cost < 0:
            raise ValueError(f"Costo negativo en arco {self.edge_id}")
        if self.risk is not None and not (0.0 <= self.risk < 1.0):
            raise ValueError(f"Riesgo fuera de dominio [0,1) en arco {self.edge_id}: {self.risk}")

    @property
    def reliability(self) -> Optional[float]:
        return None if self.risk is None else 1.0 - self.risk

@dataclass
class Graph:
    nodes: List["Node"]
    edges: List["Edge"]
    edge_indexer: Dict[str, int]

    def edge_by_id(self, edge_id: str) -> "Edge":
        return self.edges[self.edge_indexer[edge_id]]

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("El grafo no tiene nodos definidos.")
        edge_ids = [e.edge_id for e in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("Se detectaron edge_id duplicados.")

@dataclass
class RawSolution:
    path: List[str]
    edges: List[str]
    total_cost: float
    optimized_cost: float
    total_time: float
    total_risk: float

    def __post_init__(self) -> None:
        if not self.edges:
            raise ValueError("La solución debe contener al menos un arco.")
        if self.path and len(self.path) != len(self.edges) + 1:
            raise ValueError("Inconsistencia topológica: path != edges + 1")

@dataclass
class StrategicOption:
    solution: "RawSolution"
    profile: "RouteProfile"
    strategic_tags: Set["StrategicTag"] = field(default_factory=set)
    recommendation_strength: float = 0.0

@dataclass(frozen=True)
class OptimizerConfig:
    source_node_id: str
    target_node_id: str

    kappa: float = 1.0
    max_kappa: float = 100.0
    max_risk_weight: float = 50.0

    cost_weight: float = 1.0
    risk_weight: float = 1.0
    entropy_weight: float = 1.0

    cost_threshold: float = 0.05
    rigidity_threshold: float = 0.05
    entropy_threshold: float = 0.05

    rigidity_weights: Sequence[float] = (0.25, 0.25, 0.25, 0.25)
    min_redundancy: float = 0.0
    max_redundancy: float = 1.0

    strict_probabilities: bool = False
    require_full_connectivity: bool = True
    failure_assumption: FailureAssumption = FailureAssumption.INDEPENDENT
    random_seed: Optional[int] = None

    def __post_init__(self) -> None:
        if self.source_node_id == self.target_node_id:
            raise ValueError("Origen y destino no pueden ser iguales.")
        if not (0 <= self.kappa <= self.max_kappa):
            raise ValueError(f"Kappa {self.kappa} fuera de límites operativos.")
        if not math.isclose(sum(self.rigidity_weights), 1.0, rel_tol=1e-5):
            LOGGER.warning("Pesos de rigidez no normalizados. Resultado escalar puede ser inconsistente.")


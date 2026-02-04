# src/bloque3/reliability_report.py
"""
ReliabilityReport del Bloque 3.

Responsabilidad única:
    - Definir la estructura del "diploma" de confiabilidad.
    - Centralizar ranking de fragilidad, matriz de riesgo y métricas de confianza.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class ConfidenceInterval:
    mean: float
    variance: float
    alpha: float
    beta: float


@dataclass(frozen=True)
class ReliabilityReport:
    """
    Contrato de salida del Bloque 3.

    risk_matrix: matriz L_total (n x n) con confiabilidad de envío entre nodos.
    node_fragility: ranking descendente de fragilidad (más crítico primero).
    confidence_interval: intervalos por componente (nodo/arco/sistema).
    """
    risk_matrix: Sequence[Sequence[float]]
    node_fragility: Sequence[Tuple[str, float]]
    confidence_interval: Dict[str, ConfidenceInterval]
    notes: List[str] = field(default_factory=list)

    def top_fragile_nodes(self, k: int = 5) -> List[Tuple[str, float]]:
        return list(self.node_fragility[:k])


def rank_fragility(node_reliability: Mapping[str, float]) -> List[Tuple[str, float]]:
    """
    Ordena nodos desde el menos confiable (fragilidad alta) al más confiable.
    """
    items = [(node_id, 1.0 - float(score)) for node_id, score in node_reliability.items()]
    return sorted(items, key=lambda x: x[1], reverse=True)

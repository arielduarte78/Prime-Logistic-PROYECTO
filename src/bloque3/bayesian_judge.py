"""
BayesianJudge del Bloque III.

Responsabilidad única:
    - Mantener y actualizar parámetros Beta (alpha/beta) por componente.
    - Registrar éxitos/fracasos por arco, nodo y sistema.
    - Acumular impactos observados cuando ocurre una falla.
    - Proveer probabilidades de falla puras e impactos medios, nunca combinados.

Thread safety: el objeto es thread-safe gracias a un lock reentrante (RLock).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from .auditor import AuditRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BetaParams:
    alpha: float
    beta: float

    def update(self, success: bool) -> "BetaParams":
        if success:
            return BetaParams(alpha=self.alpha + 1.0, beta=self.beta)
        return BetaParams(alpha=self.alpha, beta=self.beta + 1.0)

    @property
    def mean(self) -> float:
        denom = self.alpha + self.beta
        return self.alpha / denom if denom > 0 else 0.0


@dataclass(frozen=True)
class PriorConfig:
    """Prior para componentes (optimista o no informativo)."""
    alpha: float = 1.0
    beta: float = 1.0


class BayesianJudge:
    """Acumula evidencias y actualiza confiabilidad por componente."""

    def __init__(self, prior: PriorConfig | None = None) -> None:
        self._prior = prior or PriorConfig()
        self._node_params: Dict[str, BetaParams] = {}
        self._arc_params: Dict[str, BetaParams] = {}
        self._system_params: BetaParams = BetaParams(self._prior.alpha, self._prior.beta)

        # Para cálculo de impacto (sumas acumuladas y contadores)
        self._node_impacts: Dict[str, float] = {}
        self._arc_impacts: Dict[str, float] = {}
        self._node_counts: Dict[str, int] = {}
        self._arc_counts: Dict[str, int] = {}

        # Lock reentrante para operaciones concurrentes (permite anidamiento)
        self._lock = threading.RLock()

    def _get_or_init(self, bucket: Dict[str, BetaParams], key: str) -> BetaParams:
        if key not in bucket:
            bucket[key] = BetaParams(self._prior.alpha, self._prior.beta)
        return bucket[key]

    def observe(
        self,
        audit: AuditRecord,
        failed_nodes: Iterable[str] | None = None,
        failed_arcs: Iterable[str] | None = None,
        node_impacts: Dict[str, float] | None = None,
        arc_impacts: Dict[str, float] | None = None,
    ) -> None:
        """
        Registra un escenario auditado y actualiza parámetros.

        failed_nodes / failed_arcs: IDs de componentes que fallaron.
        node_impacts / arc_impacts: diccionarios {component_id: impacto} (opcional).
        El impacto debe ser un número no negativo. Si es negativo o no numérico se lanza ValueError.
        """
        success = audit.success
        failed_nodes = list(failed_nodes or [])
        failed_arcs = list(failed_arcs or [])
        node_impacts = node_impacts or {}
        arc_impacts = arc_impacts or {}

        # Validación de impactos no negativos (las claves se normalizan a str después)
        for node_id, impact in node_impacts.items():
            if not isinstance(impact, (int, float)) or impact < 0:
                logger.error(f"Invalid node impact for {node_id}: {impact}")
                # TODO: metrics.increment("data_inconsistency", tags={"component": "node", "id": str(node_id)})
                raise ValueError(f"Invalid node impact for {node_id}: {impact} (negative or non‑numeric)")

        for arc_id, impact in arc_impacts.items():
            if not isinstance(impact, (int, float)) or impact < 0:
                logger.error(f"Invalid arc impact for {arc_id}: {impact}")
                # TODO: metrics.increment("data_inconsistency", tags={"component": "arc", "id": str(arc_id)})
                raise ValueError(f"Invalid arc impact for {arc_id}: {impact} (negative or non‑numeric)")

        with self._lock:
            # Actualización Beta tradicional (binaria) – las claves ya se normalizan a str
            for node_id in failed_nodes:
                node_str = str(node_id)
                params = self._get_or_init(self._node_params, node_str)
                self._node_params[node_str] = params.update(success=success)

            for arc_id in failed_arcs:
                arc_str = str(arc_id)
                params = self._get_or_init(self._arc_params, arc_str)
                self._arc_params[arc_str] = params.update(success=success)

            self._system_params = self._system_params.update(success=success)

            # Acumular impacto con normalización de claves a str
            for node_id, impact in node_impacts.items():
                node_str = str(node_id)
                current = self._node_impacts.get(node_str, 0.0)
                self._node_impacts[node_str] = current + impact
                self._node_counts[node_str] = self._node_counts.get(node_str, 0) + 1

            for arc_id, impact in arc_impacts.items():
                arc_str = str(arc_id)
                current = self._arc_impacts.get(arc_str, 0.0)
                self._arc_impacts[arc_str] = current + impact
                self._arc_counts[arc_str] = self._arc_counts.get(arc_str, 0) + 1

    def batch_observe(
        self,
        audits: Iterable[Tuple[AuditRecord, Mapping[str, Any]]],
    ) -> None:
        """
        Procesa múltiples escenarios.
        El segundo elemento es un payload opcional con llaves:
            - failed_nodes: List[str]
            - failed_arcs: List[str]
            - node_impacts: Dict[str, float]
            - arc_impacts: Dict[str, float]
        """
        for audit, payload in audits:
            if not isinstance(payload, Mapping):
                payload = {}

            failed_nodes = payload.get("failed_nodes")
            failed_arcs = payload.get("failed_arcs")
            node_impacts = payload.get("node_impacts")
            arc_impacts = payload.get("arc_impacts")

            self.observe(
                audit,
                failed_nodes=failed_nodes,
                failed_arcs=failed_arcs,
                node_impacts=node_impacts,
                arc_impacts=arc_impacts,
            )

    # === MÉTODOS DE EXPOSICIÓN PURA (probabilidad de falla e impacto medio) ===

    def node_failure_probability(self, node_id: str) -> float:
        """Probabilidad de falla del nodo (valor en [0,1])."""
        with self._lock:
            params = self._node_params.get(str(node_id))
            if params is None:
                return 0.0
            prob = 1.0 - params.mean
        # clamp por seguridad numérica (fuera del lock por ser operación local)
        return max(0.0, min(1.0, prob))

    def arc_failure_probability(self, arc_id: str) -> float:
        """Probabilidad de falla del arco (valor en [0,1])."""
        with self._lock:
            params = self._arc_params.get(str(arc_id))
            if params is None:
                return 0.0
            prob = 1.0 - params.mean
        return max(0.0, min(1.0, prob))

    def node_impact_mean(self, node_id: str) -> float:
        """Impacto medio condicional a que el nodo falla (≥0)."""
        node_str = str(node_id)
        with self._lock:
            if node_str not in self._node_counts or self._node_counts[node_str] == 0:
                return 0.0
            return self._node_impacts[node_str] / self._node_counts[node_str]

    def arc_impact_mean(self, arc_id: str) -> float:
        """Impacto medio condicional a que el arco falla (≥0)."""
        arc_str = str(arc_id)
        with self._lock:
            if arc_str not in self._arc_counts or self._arc_counts[arc_str] == 0:
                return 0.0
            return self._arc_impacts[arc_str] / self._arc_counts[arc_str]

    # === MÉTODOS DEPRECATED / PROHIBIDOS (lanza error) ===

    def node_fragility_with_impact(self, node_id: str) -> float:
        raise RuntimeError(
            "Fragility calculation is forbidden in Block III. "
            "Use node_failure_probability() and node_impact_mean() instead."
        )

    def arc_fragility_with_impact(self, arc_id: str) -> float:
        raise RuntimeError(
            "Fragility calculation is forbidden in Block III. "
            "Use arc_failure_probability() and arc_impact_mean() instead."
        )

    # === MÉTODOS LEGADOS (se mantienen por compatibilidad pero se recomienda no usarlos) ===
    # Los métodos node_impact_average y arc_impact_average pueden ser renombrados, pero para
    # no romper código existente se dejan como alias de los nuevos.
    def node_impact_average(self, node_id: str) -> float:
        """Alias de node_impact_mean()."""
        return self.node_impact_mean(node_id)

    def arc_impact_average(self, arc_id: str) -> float:
        """Alias de arc_impact_mean()."""
        return self.arc_impact_mean(arc_id)

    # === REPORTE PARA BLOQUE IV ===

    def reliability_report(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Exporta los datos requeridos por el Bloque IV.

        Retorna:
        {
            "edges": {
                "arc_id": {"prob_failure": 0.12, "impact_mean": 45.0},
                ...
            },
            "nodes": {
                "node_id": {"prob_failure": 0.03, "impact_mean": 0.0},
                ...
            }
        }

        Nota: todas las claves se normalizan a string internamente; el reporte refleja esa normalización.
        Este módulo nunca combina probabilidad e impacto; solo expone ambos por separado.
        """
        with self._lock:
            edges = {}
            all_arcs = set(self._arc_params.keys()) | set(self._arc_impacts.keys())
            for arc_id in all_arcs:
                edges[str(arc_id)] = {
                    "prob_failure": self.arc_failure_probability(str(arc_id)),
                    "impact_mean": self.arc_impact_mean(str(arc_id)),
                }

            nodes = {}
            all_nodes = set(self._node_params.keys()) | set(self._node_impacts.keys())
            for node_id in all_nodes:
                nodes[str(node_id)] = {
                    "prob_failure": self.node_failure_probability(str(node_id)),
                    "impact_mean": self.node_impact_mean(str(node_id)),
                }

        return {"edges": edges, "nodes": nodes}

    # === MÉTODOS EXISTENTES (con locks añadidos) ===
    def node_params(self) -> Dict[str, BetaParams]:
        with self._lock:
            return dict(self._node_params)

    def arc_params(self) -> Dict[str, BetaParams]:
        with self._lock:
            return dict(self._arc_params)

    def system_params(self) -> BetaParams:
        with self._lock:
            # system_params es inmutable, pero la referencia puede actualizarse bajo lock
            return self._system_params
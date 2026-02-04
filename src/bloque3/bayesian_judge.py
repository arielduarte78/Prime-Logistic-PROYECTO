# src/bloque3/bayesian_judge.py
"""
BayesianJudge del Bloque 3.

Responsabilidad única:
    - Mantener y actualizar parámetros Beta (alpha/beta) por componente.
    - Registrar éxitos/fracasos por arco, nodo y sistema.
    - NUEVO: Registrar impacto/severidad cuando los componentes fallan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from .auditor import AuditRecord


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
        
        # Para cálculo de impacto
        self._node_impacts: Dict[str, float] = {}
        self._arc_impacts: Dict[str, float] = {}
        self._node_counts: Dict[str, int] = {}
        self._arc_counts: Dict[str, int] = {}

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
        node_impacts / arc_impacts: diccionarios {component_id: impacto(0-1)} (opcional).
        """
        success = audit.success
        failed_nodes = list(failed_nodes or [])
        failed_arcs = list(failed_arcs or [])
        node_impacts = node_impacts or {}
        arc_impacts = arc_impacts or {}

        # 1. Actualización Beta tradicional (binaria)
        for node_id in failed_nodes:
            params = self._get_or_init(self._node_params, str(node_id))
            self._node_params[str(node_id)] = params.update(success=success)

        for arc_id in failed_arcs:
            params = self._get_or_init(self._arc_params, str(arc_id))
            self._arc_params[str(arc_id)] = params.update(success=success)

        self._system_params = self._system_params.update(success=success)

        # 2. Acumular impacto para cálculo de severidad
        for node_id, impact in node_impacts.items():
            current = self._node_impacts.get(node_id, 0.0)
            self._node_impacts[node_id] = current + impact
            self._node_counts[node_id] = self._node_counts.get(node_id, 0) + 1

        for arc_id, impact in arc_impacts.items():
            current = self._arc_impacts.get(arc_id, 0.0)
            self._arc_impacts[arc_id] = current + impact
            self._arc_counts[arc_id] = self._arc_counts.get(arc_id, 0) + 1

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

    # === MÉTODOS EXISTENTES ===
    def node_params(self) -> Dict[str, BetaParams]:
        return dict(self._node_params)

    def arc_params(self) -> Dict[str, BetaParams]:
        return dict(self._arc_params)

    def system_params(self) -> BetaParams:
        return self._system_params

    # === MÉTODOS PARA IMPACTO ===
    def node_impact_average(self, node_id: str) -> float:
        """Retorna el impacto promedio cuando este nodo falla (0-1)."""
        if node_id not in self._node_counts or self._node_counts[node_id] == 0:
            return 0.0
        return self._node_impacts[node_id] / self._node_counts[node_id]

    def arc_impact_average(self, arc_id: str) -> float:
        """Retorna el impacto promedio cuando este arco falla (0-1)."""
        if arc_id not in self._arc_counts or self._arc_counts[arc_id] == 0:
            return 0.0
        return self._arc_impacts[arc_id] / self._arc_counts[arc_id]

    def node_fragility_with_impact(self, node_id: str) -> float:
        """
        Fragilidad considerando probabilidad E impacto.
        Fórmula: P(falla) × Impacto_promedio_cuando_falla
        """
        params = self._node_params.get(node_id)
        if params is None:
            return 0.0

        # P(falla) = 1 - confiabilidad
        failure_prob = 1.0 - params.mean
        
        # Impacto promedio cuando falla
        avg_impact = self.node_impact_average(node_id)
        
        # Fragilidad = riesgo esperado
        return failure_prob * avg_impact

    def arc_fragility_with_impact(self, arc_id: str) -> float:
        """Fragilidad para arcos (con impacto)."""
        params = self._arc_params.get(arc_id)
        if params is None:
            return 0.0

        failure_prob = 1.0 - params.mean
        avg_impact = self.arc_impact_average(arc_id)
        return failure_prob * avg_impact

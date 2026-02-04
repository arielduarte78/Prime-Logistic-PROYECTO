# src/bloque3/bayesian_judge.py
"""
BayesianJudge del Bloque 3.

Responsabilidad única:
    - Mantener y actualizar parámetros Beta (alpha/beta) por componente.
    - Registrar éxitos/fracasos por arco, nodo y sistema.
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

    def _get_or_init(self, bucket: Dict[str, BetaParams], key: str) -> BetaParams:
        if key not in bucket:
            bucket[key] = BetaParams(self._prior.alpha, self._prior.beta)
        return bucket[key]

    def observe(
        self,
        audit: AuditRecord,
        failed_nodes: Iterable[str] | None = None,
        failed_arcs: Iterable[str] | None = None,
    ) -> None:
        """
        Registra un escenario auditado y actualiza parámetros.

        failed_nodes / failed_arcs pueden venir del escenario (nodos/arcos degradados).
        """
        success = audit.success
        failed_nodes = list(failed_nodes or [])
        failed_arcs = list(failed_arcs or [])

        for node_id in failed_nodes:
            params = self._get_or_init(self._node_params, str(node_id))
            self._node_params[str(node_id)] = params.update(success=success)

        for arc_id in failed_arcs:
            params = self._get_or_init(self._arc_params, str(arc_id))
            self._arc_params[str(arc_id)] = params.update(success=success)

        self._system_params = self._system_params.update(success=success)

    def batch_observe(
        self,
        audits: Iterable[Tuple[AuditRecord, Mapping[str, Any]]],
    ) -> None:
        """
        Procesa múltiples escenarios.
        El segundo elemento es un payload opcional con llaves:
            - failed_nodes: List[str]
            - failed_arcs: List[str]
        """
        for audit, payload in audits:
            failed_nodes = payload.get("failed_nodes") if isinstance(payload, Mapping) else None
            failed_arcs = payload.get("failed_arcs") if isinstance(payload, Mapping) else None
            self.observe(audit, failed_nodes=failed_nodes, failed_arcs=failed_arcs)

    def node_params(self) -> Dict[str, BetaParams]:
        return dict(self._node_params)

    def arc_params(self) -> Dict[str, BetaParams]:
        return dict(self._arc_params)

    def system_params(self) -> BetaParams:
        return self._system_params

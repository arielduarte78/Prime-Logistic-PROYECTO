# src/bloque3/inference_engine.py
"""
InferenceEngine del Bloque 3.

Responsabilidad única:
    - Orquestar auditoría + actualización bayesiana.
    - Generar ReliabilityReport consumible por el resto del sistema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .auditor import AuditRecord, FailureCriteria, audit_scenarios
from .bayesian_judge import BayesianJudge, BetaParams, PriorConfig
from .reliability_report import ConfidenceInterval, ReliabilityReport, rank_fragility


@dataclass(frozen=True)
class InferenceConfig:
    criteria: FailureCriteria = FailureCriteria()
    prior: PriorConfig = PriorConfig()


def _beta_variance(params: BetaParams) -> float:
    a = params.alpha
    b = params.beta
    denom = (a + b) ** 2 * (a + b + 1.0)
    if denom <= 0:
        return 0.0
    return (a * b) / denom


def _params_to_interval(params: BetaParams) -> ConfidenceInterval:
    return ConfidenceInterval(
        mean=params.mean,
        variance=_beta_variance(params),
        alpha=params.alpha,
        beta=params.beta,
    )


def _component_mean(params: BetaParams | None, prior: PriorConfig) -> float:
    if params is None:
        denom = prior.alpha + prior.beta
        return prior.alpha / denom if denom > 0 else 0.0
    return params.mean


class InferenceEngine:
    """
    Orquesta el Bloque 3:
        - clasifica escenarios (auditor)
        - actualiza parámetros beta (judge)
        - emite ReliabilityReport
    """

    def __init__(self, config: InferenceConfig | None = None) -> None:
        self._config = config or InferenceConfig()
        self._judge = BayesianJudge(prior=self._config.prior)

    def process(
        self,
        scenarios: Iterable[Dict[str, Any]],
        *,
        scenario_payloads: Mapping[str, Mapping[str, Any]] | None = None,
        node_index: Sequence[str] | None = None,
    ) -> ReliabilityReport:
        """
        scenarios: iterable de dicts de escenarios.
        scenario_payloads: info extra opcional (failed_nodes/failed_arcs) por scenario_id.
        node_index: orden de nodos para construir risk_matrix (si no se pasa, queda vacío).
        """
        scenario_payloads = scenario_payloads or {}
        audits = audit_scenarios(scenarios, criteria=self._config.criteria)

        batched: List[Tuple[AuditRecord, Mapping[str, Any]]] = []
        for audit in audits:
            payload = scenario_payloads.get(audit.scenario_id, {})
            batched.append((audit, payload))

        self._judge.batch_observe(batched)

        node_params = self._judge.node_params()
        arc_params = self._judge.arc_params()
        system_params = self._judge.system_params()

        node_reliability = {
            node_id: _component_mean(node_params.get(node_id), self._config.prior)
            for node_id in (node_index or [])
        }
        node_fragility = rank_fragility(node_reliability)

        risk_matrix: List[List[float]] = []
        if node_index:
            system_mean = _component_mean(system_params, self._config.prior)
            for origin in node_index:
                row: List[float] = []
                origin_mean = _component_mean(node_params.get(origin), self._config.prior)
                for dest in node_index:
                    dest_mean = _component_mean(node_params.get(dest), self._config.prior)
                    arc_key = f"{origin}->{dest}"
                    arc_mean = _component_mean(arc_params.get(arc_key), self._config.prior)
                    row.append(arc_mean * origin_mean * dest_mean * system_mean)
                risk_matrix.append(row)

        confidence_interval: Dict[str, ConfidenceInterval] = {
            **{f"node:{nid}": _params_to_interval(params) for nid, params in node_params.items()},
            **{f"arc:{aid}": _params_to_interval(params) for aid, params in arc_params.items()},
            "system": _params_to_interval(system_params),
        }

        notes = [
            "risk_matrix usa arco clave 'origin->dest' si se provee node_index.",
            "node_fragility se basa en (1 - confiabilidad) por nodo.",
        ]

        return ReliabilityReport(
            risk_matrix=risk_matrix,
            node_fragility=node_fragility,
            confidence_interval=confidence_interval,
            notes=notes,
        )
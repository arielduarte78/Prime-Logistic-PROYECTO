# src/bloque3/inference_engine.py
"""
InferenceEngine del Bloque 3.

Responsabilidad única:
    - Orquestar auditoría + actualización bayesiana.
    - Generar ReliabilityReport consumible por el resto del sistema.
    - NUEVO: Considerar impacto/severidad en cálculos de fragilidad.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .auditor import AuditRecord, FailureCriteria, audit_scenarios
from .bayesian_judge import BayesianJudge, BetaParams, PriorConfig
from .reliability_report import ConfidenceInterval, ReliabilityReport


@dataclass(frozen=True)
class InferenceConfig:
    criteria: FailureCriteria = FailureCriteria()
    prior: PriorConfig = PriorConfig()
    use_impact_in_fragility: bool = True  # NUEVO: Control para usar impacto


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
        scenario_payloads: info extra opcional (failed_nodes/failed_arcs/node_impacts/arc_impacts).
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

        # NUEVO: Cálculo de fragilidad CON o SIN impacto
        node_fragility: List[Tuple[str, float]] = []
        
        if self._config.use_impact_in_fragility:
            # CON IMPACTO: Usar el nuevo método que considera probabilidad × impacto
            for node_id in (node_index or []):
                fragility = self._judge.node_fragility_with_impact(node_id)
                node_fragility.append((node_id, fragility))
        else:
            # SIN IMPACTO: Método original (binario)
            node_reliability = {
                node_id: _component_mean(node_params.get(node_id), self._config.prior)
                for node_id in (node_index or [])
            }
            # Fragilidad = 1 - confiabilidad
            node_fragility = [
                (node_id, 1.0 - reliability) 
                for node_id, reliability in node_reliability.items()
            ]
        
        # Ordenar por fragilidad (mayor primero)
        node_fragility.sort(key=lambda x: x[1], reverse=True)

        # NUEVO: Matriz de riesgo usando fragilidad con impacto
        risk_matrix: List[List[float]] = []
        if node_index:
            if self._config.use_impact_in_fragility:
                # Usar fragilidad con impacto en matriz de riesgo
                for origin in node_index:
                    row: List[float] = []
                    origin_frag = self._judge.node_fragility_with_impact(origin)
                    for dest in node_index:
                        dest_frag = self._judge.node_fragility_with_impact(dest)
                        arc_key = f"{origin}->{dest}"
                        arc_frag = self._judge.arc_fragility_with_impact(arc_key)
                        
                        # Riesgo combinado: probabilidad de que al menos uno falle con impacto
                        # Fórmula: 1 - (1-frag_origin)*(1-frag_dest)*(1-frag_arc)
                        combined_risk = 1 - (1-origin_frag)*(1-dest_frag)*(1-arc_frag)
                        row.append(combined_risk)
                    risk_matrix.append(row)
            else:
                # Método original (sin impacto)
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
            f"risk_matrix usando {'impacto+probabilidad' if self._config.use_impact_in_fragility else 'confiabilidad binaria'}.",
            f"node_fragility calculada con {'impacto' if self._config.use_impact_in_fragility else '(1 - confiabilidad)'}.",
            "Para usar impacto, asegurar que scenario_payloads incluya node_impacts/arc_impacts.",
        ]

        return ReliabilityReport(
            risk_matrix=risk_matrix,
            node_fragility=node_fragility,
            confidence_interval=confidence_interval,
            notes=notes,
        )
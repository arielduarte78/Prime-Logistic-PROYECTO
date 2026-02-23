#inference_engine.py
"""
InferenceEngine del Bloque III.

Responsabilidad única:
    - Orquestar auditoría y actualización bayesiana.
    - Consumir y validar el reliability_report() del BayesianJudge.
    - Exponer hacia Bloque IV los pares (prob_failure, impact_mean) sin combinarlos.
    - No realizar ninguna fusión de probabilidad e impacto.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .auditor import AuditRecord, FailureCriteria, audit_scenarios
from .bayesian_judge import BayesianJudge, BetaParams, PriorConfig
from .reliability_report import ConfidenceInterval, ReliabilityReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InferenceConfig:
    criteria: FailureCriteria = FailureCriteria()
    prior: PriorConfig = PriorConfig()
    # Nota: se eliminó use_impact_in_fragility; el bloque III ya no combina P e I.


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
    # kept for future use (not used in process() currently)
    if params is None:
        denom = prior.alpha + prior.beta
        return prior.alpha / denom if denom > 0 else 0.0
    return params.mean


class InferenceEngine:
    """
    Orquesta el Bloque III:
        - clasifica escenarios (auditor)
        - actualiza parámetros beta (judge)
        - consume reliability_report() del judge y valida su estructura
        - emite ReliabilityReport con risk_matrix vacío y node_fragility vacío,
          y añade notas aclaratorias; los pares (prob_failure, impact_mean) se
          exponen exclusivamente a través del método reliability_report() del judge,
          que debe ser utilizado directamente por el Bloque IV.
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
        Procesa escenarios, actualiza el judge y devuelve un reporte.

        Nota: risk_matrix y node_fragility se devuelven vacíos, ya que el bloque III
        no debe combinar probabilidad e impacto. Los pares (prob_failure, impact_mean)
        están disponibles a través del método reliability_report() del BayesianJudge,
        que debe ser usado por el Bloque IV para obtener los valores validados por
        componente.

        El método reliability_report() del judge está envuelto en un bloque try/except
        para garantizar trazabilidad en caso de fallos inesperados.
        """
        scenario_payloads = scenario_payloads or {}
        audits = audit_scenarios(scenarios, criteria=self._config.criteria)

        batched: List[Tuple[AuditRecord, Mapping[str, Any]]] = []
        for audit in audits:
            payload = scenario_payloads.get(audit.scenario_id, {})
            batched.append((audit, payload))

        self._judge.batch_observe(batched)

        # 1. Obtener el reporte canónico del judge con wrap defensivo
        try:
            report = self._judge.reliability_report()
        except Exception as e:
            logger.exception("Unexpected error while calling reliability_report()")
            raise RuntimeError("Failed to obtain reliability report from BayesianJudge") from e

        # 2. Validar estructura mínima
        if not isinstance(report, dict) or "edges" not in report or "nodes" not in report:
            msg = "Invalid reliability_report() structure from BayesianJudge: expected {'edges','nodes'}"
            logger.error(msg)
            raise RuntimeError(msg)

        edges_report = report["edges"]
        nodes_report = report["nodes"]

        if not isinstance(edges_report, dict) or not isinstance(nodes_report, dict):
            msg = "Invalid reliability_report() types: 'edges' and 'nodes' must be dicts"
            logger.error(msg)
            raise RuntimeError(msg)

        # 3. Validar cada arco con normalización de clave y rechazo de NaN/Inf
        for arc_id, payload in edges_report.items():
            arc_key = str(arc_id)
            if not isinstance(payload, Mapping):
                msg = f"Invalid edge payload for {arc_key}: expected mapping"
                logger.error(msg)
                raise RuntimeError(msg)
            if "prob_failure" not in payload or "impact_mean" not in payload:
                msg = f"Edge {arc_key} missing required keys 'prob_failure'/'impact_mean'"
                logger.error(msg)
                raise RuntimeError(msg)
            prob = payload["prob_failure"]
            impact = payload["impact_mean"]
            if not isinstance(prob, (int, float)) or prob < 0.0 or prob > 1.0:
                msg = f"Edge {arc_key} prob_failure out of range: {prob}"
                logger.error(msg)
                raise ValueError(msg)
            if not isinstance(impact, (int, float)) or impact < 0.0:
                msg = f"Edge {arc_key} impact_mean must be non-negative: {impact}"
                logger.error(msg)
                raise ValueError(msg)
            if not math.isfinite(float(prob)):
                msg = f"Edge {arc_key} prob_failure is not finite: {prob}"
                logger.error(msg)
                raise ValueError(msg)
            if not math.isfinite(float(impact)):
                msg = f"Edge {arc_key} impact_mean is not finite: {impact}"
                logger.error(msg)
                raise ValueError(msg)

        # 4. Validar cada nodo con normalización de clave y rechazo de NaN/Inf
        for node_id, payload in nodes_report.items():
            node_key = str(node_id)
            if not isinstance(payload, Mapping):
                msg = f"Invalid node payload for {node_key}: expected mapping"
                logger.error(msg)
                raise RuntimeError(msg)
            if "prob_failure" not in payload or "impact_mean" not in payload:
                msg = f"Node {node_key} missing required keys 'prob_failure'/'impact_mean'"
                logger.error(msg)
                raise RuntimeError(msg)
            prob = payload["prob_failure"]
            impact = payload["impact_mean"]
            if not isinstance(prob, (int, float)) or prob < 0.0 or prob > 1.0:
                msg = f"Node {node_key} prob_failure out of range: {prob}"
                logger.error(msg)
                raise ValueError(msg)
            if not isinstance(impact, (int, float)) or impact < 0.0:
                msg = f"Node {node_key} impact_mean must be non-negative: {impact}"
                logger.error(msg)
                raise ValueError(msg)
            if not math.isfinite(float(prob)):
                msg = f"Node {node_key} prob_failure is not finite: {prob}"
                logger.error(msg)
                raise ValueError(msg)
            if not math.isfinite(float(impact)):
                msg = f"Node {node_key} impact_mean is not finite: {impact}"
                logger.error(msg)
                raise ValueError(msg)

        # 5. Construir intervalos de confianza (igual que antes)
        node_params = self._judge.node_params()
        arc_params = self._judge.arc_params()
        system_params = self._judge.system_params()

        confidence_interval: Dict[str, ConfidenceInterval] = {
            **{f"node:{nid}": _params_to_interval(params) for nid, params in node_params.items()},
            **{f"arc:{aid}": _params_to_interval(params) for aid, params in arc_params.items()},
            "system": _params_to_interval(system_params),
        }

        # 6. Preparar el reporte final: risk_matrix y node_fragility vacíos
        risk_matrix: List[List[float]] = []  # vacío por diseño
        node_fragility: List[Tuple[str, float]] = []  # vacío por diseño

        notes = [
            "Reliability report consumed from BayesianJudge; P(F) and impact_mean are exposed separately.",
            "No fusion of probability and impact performed in Block III; downstream blocks must decide how to combine.",
            "risk_matrix and node_fragility are left empty intentionally. Use BayesianJudge.reliability_report() directly.",
        ]

        # NOTE: risk_matrix and node_fragility intentionally empty; downstream must use
        # BayesianJudge.reliability_report() for (prob_failure, impact_mean) pairs.

        return ReliabilityReport(
            risk_matrix=risk_matrix,
            node_fragility=node_fragility,
            confidence_interval=confidence_interval,
            notes=notes,
        )
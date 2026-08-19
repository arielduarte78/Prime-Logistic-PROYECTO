"""stochopti/bayesian/inference.py — Bayesian Inference Orchestrator."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from stochopti.core.types import BetaPrior
from stochopti.core.protocols import ScenarioClassifier
from stochopti.bayesian.engine import BayesianRiskEngine

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ConfidenceInterval:
    mean: float
    variance: float
    alpha: float
    beta: float

@dataclass
class ReliabilityReport:
    risk_matrix: List[List[float]]
    node_fragility: List[Tuple[str, float]]
    confidence_interval: Dict[str, ConfidenceInterval]
    notes: List[str]

def _params_to_interval(params: BetaPrior) -> ConfidenceInterval:
    return ConfidenceInterval(
        mean=params.mean,
        variance=params.variance,
        alpha=params.alpha,
        beta=params.beta,
    )

class InferenceOrchestrator:
    """Orquesta las observaciones de escenarios y actualizaciones de riesgo."""
    
    def __init__(
        self,
        classifier: ScenarioClassifier,
        engine: BayesianRiskEngine
    ) -> None:
        self.classifier = classifier
        self.engine = engine

    def process(
        self,
        scenarios: Iterable[Dict[str, Any]],
        scenario_payloads: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> ReliabilityReport:
        """
        Clasifica escenarios y emite actualizaciones en batch al motor bayesiano.
        """
        scenario_payloads = scenario_payloads or {}
        
        class SimpleAuditRecord:
            def __init__(self, success: bool):
                self.success = success
                
        batched = []
        for scenario in scenarios:
            scenario_id = scenario.get("scenario_id", str(id(scenario)))
            success, reasons = self.classifier.classify(scenario)
            
            audit = SimpleAuditRecord(success=success)
            payload = scenario_payloads.get(scenario_id, {})
            batched.append((audit, payload))

        self.engine.batch_observe(batched)

        try:
            report = self.engine.reliability_report()
        except Exception as e:
            logger.exception("Unexpected error while calling reliability_report()")
            raise RuntimeError("Failed to obtain reliability report from engine") from e

        node_params = self.engine.node_params()
        arc_params = self.engine.arc_params()
        system_params = self.engine.system_params()

        confidence_interval: Dict[str, ConfidenceInterval] = {
            **{f"node:{nid}": _params_to_interval(params) for nid, params in node_params.items()},
            **{f"arc:{aid}": _params_to_interval(params) for aid, params in arc_params.items()},
            "system": _params_to_interval(system_params),
        }

        notes = [
            "Reliability report consumed from BayesianRiskEngine.",
            "risk_matrix and node_fragility are left empty intentionally for external synthesis."
        ]

        return ReliabilityReport(
            risk_matrix=[],
            node_fragility=[],
            confidence_interval=confidence_interval,
            notes=notes,
        )

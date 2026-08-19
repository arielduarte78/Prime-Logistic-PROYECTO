"""stochopti/montecarlo/auditor.py — Agnostic Scenario Classifier."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from stochopti.core.protocols import ScenarioClassifier

@dataclass(frozen=True)
class ClassificationRule:
    """Regla dinámica de umbral para clasificar métricas abstractas."""
    metric_key: str
    baseline_key: Optional[str]
    threshold: float
    operator: str  # '<', '<=', '>', '>='

class RuleBasedClassifier(ScenarioClassifier):
    """Clasificador de escenarios basado en umbrales inyectables."""
    
    def __init__(self, rules: List[ClassificationRule]):
        self.rules = rules

    def classify(self, scenario: Dict[str, Any]) -> Tuple[bool, Tuple[str, ...]]:
        reasons = []
        metrics = scenario.get("metrics", scenario)
        
        for rule in self.rules:
            val = metrics.get(rule.metric_key)
            if val is None:
                continue
                
            limit = rule.threshold
            if rule.baseline_key:
                base_val = metrics.get(rule.baseline_key)
                if base_val is None:
                    continue
                limit = base_val * rule.threshold

            failed = False
            if rule.operator == '<' and val < limit: failed = True
            elif rule.operator == '<=' and val <= limit: failed = True
            elif rule.operator == '>' and val > limit: failed = True
            elif rule.operator == '>=' and val >= limit: failed = True
            
            if failed:
                reasons.append(f"{rule.metric_key}_{rule.operator}_{rule.threshold}")
                
        return (len(reasons) == 0, tuple(reasons))

def batch_audit(
    scenarios: List[Dict[str, Any]], 
    classifier: ScenarioClassifier
) -> List[Dict[str, Any]]:
    """Aplica el clasificador a una lista de escenarios."""
    results = []
    for sc in scenarios:
        success, reasons = classifier.classify(sc)
        # Se genera un record ligero compatible con duck-typing del motor bayesiano
        results.append({
            "scenario_id": sc.get("scenario_id", "unknown"),
            "success": success,
            "reasons": reasons,
            "metrics": sc.get("metrics", {})
        })
    return results

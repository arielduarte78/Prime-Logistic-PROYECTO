# src/bloque3/auditor.py
"""
Auditor forense del Bloque 3.

Responsabilidad única:
    - Leer scenarios.pkl
    - Clasificar cada escenario como Éxito/Fracaso

Este módulo no calcula Bayes ni reportes; solo etiqueta escenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import pickle


@dataclass(frozen=True)
class FailureCriteria:
    """Umbrales industriales para declarar un escenario como fallido."""
    min_capacity_retained: float = 0.85
    max_time_multiplier: float = 1.4
    max_cost_multiplier: float = 1.5


@dataclass(frozen=True)
class AuditRecord:
    """Resultado de auditoría para un escenario."""
    scenario_id: str
    success: bool
    reasons: Tuple[str, ...]
    metrics: Dict[str, Any]


def load_scenarios(path: str) -> Sequence[Dict[str, Any]]:
    """Carga un archivo pickle con la lista de escenarios."""
    with open(path, "rb") as handle:
        data = pickle.load(handle)
    if not isinstance(data, (list, tuple)):
        raise ValueError("scenarios.pkl debe contener una lista/tupla de escenarios")
    return data


def _read_metric(scenario: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = scenario.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    metrics = scenario.get("metrics")
    if isinstance(metrics, dict):
        for key in keys:
            value = metrics.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return None


def classify_scenario(
    scenario: Dict[str, Any],
    criteria: FailureCriteria,
    default_id: str,
) -> AuditRecord:
    scenario_id = str(scenario.get("id") or scenario.get("scenario_id") or default_id)

    capacity_retained = _read_metric(scenario, "capacity_retained", "capacity_ratio")
    travel_time = _read_metric(scenario, "travel_time", "avg_travel_time")
    base_time = _read_metric(scenario, "base_time", "baseline_time")
    total_cost = _read_metric(scenario, "total_cost", "cost")
    base_cost = _read_metric(scenario, "base_cost", "baseline_cost")

    reasons: List[str] = []

    if capacity_retained is not None and capacity_retained < criteria.min_capacity_retained:
        reasons.append("capacity_retained_below_threshold")

    if travel_time is not None and base_time is not None:
        if travel_time > base_time * criteria.max_time_multiplier:
            reasons.append("travel_time_above_threshold")

    if total_cost is not None and base_cost is not None:
        if total_cost > base_cost * criteria.max_cost_multiplier:
            reasons.append("cost_above_threshold")

    success = len(reasons) == 0
    metrics = {
        "capacity_retained": capacity_retained,
        "travel_time": travel_time,
        "base_time": base_time,
        "total_cost": total_cost,
        "base_cost": base_cost,
    }

    return AuditRecord(
        scenario_id=scenario_id,
        success=success,
        reasons=tuple(reasons),
        metrics=metrics,
    )


def audit_scenarios(
    scenarios: Iterable[Dict[str, Any]],
    criteria: Optional[FailureCriteria] = None,
) -> List[AuditRecord]:
    criteria = criteria or FailureCriteria()
    records: List[AuditRecord] = []
    for idx, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            raise ValueError(f"Escenario inválido en posición {idx}: se esperaba dict")
        record = classify_scenario(scenario, criteria, default_id=f"scenario_{idx}")
        records.append(record)
    return records
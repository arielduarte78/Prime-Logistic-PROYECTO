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
import logging

LOGGER = logging.getLogger(__name__)


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
    """Carga un archivo pickle y extrae la lista de escenarios con resiliencia.

    Soporta:
      - lista/tupla directa
      - objetos que envuelven la lista en atributos comunes: 'scenarios', 'items', 'records', 'data'
    Lanza ValueError si no se encuentra una estructura compatible.
    """
    try:
        with open(path, "rb") as handle:
            data = pickle.load(handle)
    except FileNotFoundError:
        raise
    except pickle.UnpicklingError as exc:
        LOGGER.exception("Error desempaquetando %s: %s", path, exc)
        raise ValueError("Archivo de escenarios corrupto o no es un pickle válido.") from exc
    except Exception as exc:
        LOGGER.exception("Error leyendo %s: %s", path, exc)
        raise

    # 1. Caso ideal: es una lista directa
    if isinstance(data, (list, tuple)):
        return list(data)

    # 2. Caso robusto: la data está envuelta en un objeto (sniffing de atributos)
    for attr in ("scenarios", "items", "records", "data"):
        value = getattr(data, attr, None)
        if isinstance(value, (list, tuple)):
            return list(value)

    # 3. Caso: dict con clave 'scenarios'
    if isinstance(data, dict) and "scenarios" in data and isinstance(data["scenarios"], (list, tuple)):
        return list(data["scenarios"])

    raise ValueError("scenarios.pkl no contiene una estructura de datos compatible.")


def _read_metric(scenario: Dict[str, Any], *keys: str) -> Optional[float]:
    """Lee de forma defensiva una métrica numérica desde el dict del escenario."""
    if not isinstance(scenario, dict):
        return None

    for key in keys:
        value = scenario.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        # Aceptar strings numéricas
        if isinstance(value, str):
            try:
                return float(value)
            except Exception:
                continue

    metrics = scenario.get("metrics")
    if isinstance(metrics, dict):
        for key in keys:
            value = metrics.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except Exception:
                    continue
    return None


def classify_scenario(
    scenario: Dict[str, Any],
    criteria: FailureCriteria,
    default_id: str,
) -> AuditRecord:
    """Clasifica un escenario según criterios industriales y devuelve un AuditRecord."""
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
        try:
            if travel_time > base_time * criteria.max_time_multiplier:
                reasons.append("travel_time_above_threshold")
        except Exception:
            LOGGER.debug("Error comparando travel_time/base_time en escenario %s", scenario_id)

    if total_cost is not None and base_cost is not None:
        try:
            if total_cost > base_cost * criteria.max_cost_multiplier:
                reasons.append("cost_above_threshold")
        except Exception:
            LOGGER.debug("Error comparando total_cost/base_cost en escenario %s", scenario_id)

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
    """Aplica la clasificación a una colección de escenarios.

    Comportamiento defensivo:
      - Si un elemento no es dict, se registra una advertencia y se omite.
      - No interrumpe el procesamiento por un escenario mal formado.
    """
    criteria = criteria or FailureCriteria()
    records: List[AuditRecord] = []
    for idx, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            LOGGER.warning("Escenario en posición %d no es un dict; se omite.", idx)
            continue
        try:
            record = classify_scenario(scenario, criteria, default_id=f"scenario_{idx}")
            records.append(record)
        except Exception:
            LOGGER.exception("Error clasificando escenario en posición %d; se omite.", idx)
            continue
    return records

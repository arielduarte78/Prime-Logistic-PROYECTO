# src/bloque4/weight_builder.py
from __future__ import annotations

import math
import logging
from typing import Iterable, Mapping, Any

from .schema import Edge

logger = logging.getLogger(__name__)

# Seguridad numérica: epsilon para evitar log(0) y límites
_P_EPS = 1e-12
_P_MAX = 1.0 - 1e-12

def _safe_prob(p: float) -> float:
    """Clamp probability into (0, 1) open interval with tiny epsilon safety."""
    try:
        pf = float(p)
    except Exception:
        raise ValueError(f"Probability value is not numeric: {p!r}")
    if pf <= 0.0:
        return 0.0
    if pf >= 1.0:
        return _P_MAX
    return max(_P_EPS, min(_P_MAX, pf))

def build_weights(edges: Iterable[Edge], reliability_report: Mapping[str, Mapping[str, Any]]) -> None:
    """
    Itera una sola vez sobre 'edges' y actualiza in-place:
      - edge.w_survival = -ln(1 - P(F))  (clamped con epsilon)
      - edge.w_expected_cost = cost + P(F) * impact_mean

    Args:
        edges: iterable de objetos Edge (mutables).
        reliability_report: dict con la estructura {'edges': {edge_id: {'prob_failure':..., 'impact_mean':...}}, 'nodes': {...}}
    Raises:
        RuntimeError / ValueError si la estructura del reporte es inválida o faltan claves.
    """
    if not isinstance(reliability_report, Mapping) or "edges" not in reliability_report:
        raise RuntimeError("Invalid reliability_report: missing 'edges' mapping")

    edges_report = reliability_report["edges"]
    if not isinstance(edges_report, Mapping):
        raise RuntimeError("Invalid reliability_report: 'edges' must be a mapping")

    for edge in edges:
        eid = str(edge.edge_id)
        payload = edges_report.get(eid)
        if payload is None:
            # No hay datos para este arco; dejamos los pesos por defecto y continuamos.
            continue

        if not isinstance(payload, Mapping):
            raise RuntimeError(f"Invalid payload for edge {eid}: expected mapping")

        if "prob_failure" not in payload or "impact_mean" not in payload:
            raise RuntimeError(f"Edge {eid} missing 'prob_failure' or 'impact_mean' in reliability_report")

        prob = payload["prob_failure"]
        impact = payload["impact_mean"]

        # Convertir y validar numéricamente
        try:
            prob_f = float(prob)
        except Exception:
            raise ValueError(f"Edge {eid} prob_failure is not numeric: {prob!r}")
        try:
            impact_f = float(impact)
        except Exception:
            raise ValueError(f"Edge {eid} impact_mean is not numeric: {impact!r}")

        # Clamp / seguridad
        prob_safe = _safe_prob(prob_f)

        # Eje supervivencia: -ln(1 - p) con seguridad numérica
        if prob_safe <= 0.0:
            w_surv = 0.0
        else:
            w_surv = -math.log(1.0 - prob_safe)

        # Eje fricción/operativo: cost + p * impact_mean
        w_expected = float(edge.cost) + prob_f * impact_f

        # Asignar in-place
        try:
            edge.w_survival = float(w_surv)
            edge.w_expected_cost = float(w_expected)
        except Exception:
            logger.exception("Failed to assign weights to edge %s. Is Edge dataclass frozen?", eid)
            raise RuntimeError("Edge objects appear immutable; make Edge mutable or adapt weight_builder to return weights mapping")

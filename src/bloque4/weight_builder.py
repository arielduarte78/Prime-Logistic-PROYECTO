from __future__ import annotations

import math
import logging
from typing import Iterable, Mapping, Any

from .schema import Edge

LOGGER = logging.getLogger(__name__)

# Seguridad numérica: epsilon para evitar log(0) y límites
_P_EPS = 1e-12
_P_MAX = 1.0 - 1e-12


def _safe_prob(p: float) -> float:
    """Clamp probability into [0, 1) with tiny epsilon safety for log."""
    try:
        pf = float(p)
    except Exception:
        raise ValueError(f"Probability value is not numeric: {p!r}")
    if pf <= 0.0:
        return 0.0
    if pf >= 1.0:
        return _P_MAX
    return max(_P_EPS, min(_P_MAX, pf))


def build_edge_weights(edges: Iterable[Edge], reliability_report: Mapping[str, Mapping[str, Any]]) -> None:
    """
    Itera una sola vez sobre 'edges' y actualiza in-place:
      - edge.w_survival = -ln(1 - P(F))  (clamped con epsilon)
      - edge.w_expected_cost = cost + P_safe * impact_mean

    Args:
        edges: iterable de objetos Edge (mutables).
        reliability_report: dict con la estructura
            {'edges': {edge_id: {'prob_failure': float, 'impact_mean': float}}, ...}

    Notes:
        - Si un edge no tiene entrada en el reporte, se deja sin modificar.
        - Si Edge resulta inmutable, se lanza RuntimeError con mensaje claro.
    """
    if not isinstance(reliability_report, Mapping) or "edges" not in reliability_report:
        raise RuntimeError("Invalid reliability_report: missing 'edges' mapping")

    edges_report = reliability_report["edges"]
    if not isinstance(edges_report, Mapping):
        raise RuntimeError("Invalid reliability_report: 'edges' must be a mapping")

    for edge in edges:
        eid = str(getattr(edge, "edge_id", None))
        if not eid:
            LOGGER.debug("Encountered edge without edge_id; skipping.")
            continue

        payload = edges_report.get(eid)
        if payload is None:
            LOGGER.debug("No reliability data for edge %s; skipping weight assignment.", eid)
            continue

        if not isinstance(payload, Mapping):
            LOGGER.warning("Invalid payload type for edge %s; expected mapping, got %s. Skipping.", eid, type(payload))
            continue

        # Accept payloads that may use alternative keys
        prob_key = "prob_failure" if "prob_failure" in payload else ("p_fail" if "p_fail" in payload else None)
        impact_key = "impact_mean" if "impact_mean" in payload else ("impact" if "impact" in payload else None)

        if prob_key is None or impact_key is None:
            LOGGER.warning("Edge %s missing 'prob_failure' or 'impact_mean' keys; skipping.", eid)
            continue

        prob = payload.get(prob_key)
        impact = payload.get(impact_key)

        # Convertir y validar numéricamente
        try:
            prob_f = float(prob)
        except Exception:
            LOGGER.warning("Edge %s prob_failure is not numeric: %r; skipping.", eid, prob)
            continue
        try:
            impact_f = float(impact)
        except Exception:
            LOGGER.warning("Edge %s impact_mean is not numeric: %r; skipping.", eid, impact)
            continue

        # Clamp / seguridad
        prob_safe = _safe_prob(prob_f)

        # Eje supervivencia: -ln(1 - p) con seguridad numérica
        w_surv = -math.log(1.0 - prob_safe) if prob_safe > 0.0 else 0.0

        # Eje fricción/operativo: cost + p_safe * impact_mean
        # Defensive cost extraction
        try:
            cost_val = float(getattr(edge, "cost", 0.0) or 0.0)
        except Exception:
            LOGGER.warning("Edge %s has non-numeric cost; defaulting to 0.0", eid)
            cost_val = 0.0

        w_expected = cost_val + prob_safe * float(impact_f)

        # Asignar in-place; si Edge es inmutable, lanzar RuntimeError con mensaje claro
        try:
            setattr(edge, "w_survival", float(w_surv))
            setattr(edge, "w_expected_cost", float(w_expected))
            LOGGER.debug(
                "Assigned weights to edge %s: w_survival=%.6f w_expected_cost=%.6f",
                eid, w_surv, w_expected
            )
        except Exception:
            LOGGER.exception("Failed to assign weights to edge %s. Edge may be immutable.", eid)
            raise RuntimeError("Edge objects appear immutable; make Edge mutable or adapt weight_builder to return weights mapping")

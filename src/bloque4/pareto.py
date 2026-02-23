from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Dict, Any
import math

from .schema import RawSolution

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParetoSolution:
    """Inmutable: representación de una solución reconstruida desde una etiqueta."""
    path: Sequence[str]
    edges: Sequence[str]
    total_cost: float
    optimized_cost: float
    total_time: float
    total_risk: float
    w_survival: float
    w_expected_cost: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": list(self.path),
            "edges": list(self.edges),
            "total_cost": float(self.total_cost),
            "optimized_cost": float(self.optimized_cost),
            "total_time": float(self.total_time),
            "total_risk": float(self.total_risk),
            "w_survival": float(self.w_survival),
            "w_expected_cost": float(self.w_expected_cost),
        }


@dataclass
class ParetoFrontResult:
    """Contiene la frontera reconstruida y utilidades para extraer arquetipos."""
    solutions: List[ParetoSolution] = field(default_factory=list)

    @classmethod
    def from_labels(cls, labels: Sequence, engine: Any) -> "ParetoFrontResult":
        """
        Construye ParetoFrontResult a partir de una lista de Label y un engine que
        provea reconstruct_path(label) -> RawSolution.

        Esta implementación es defensiva: si la reconstrucción falla para una etiqueta,
        se registra y se omite esa etiqueta en lugar de romper todo el proceso.
        """
        sols: List[ParetoSolution] = []
        for lbl in labels or []:
            try:
                raw: RawSolution = engine.reconstruct_path(lbl)
            except Exception as exc:
                LOGGER.exception("Failed to reconstruct RawSolution from label: %s", exc)
                continue

            # Defensive extraction of label numeric axes
            w_surv = float(getattr(lbl, "w_survival", getattr(lbl, "cum_risk_weight", 0.0) or 0.0))
            w_exp = float(getattr(lbl, "w_expected_cost", getattr(lbl, "cum_cost", 0.0) or 0.0))

            try:
                sols.append(
                    ParetoSolution(
                        path=tuple(getattr(raw, "path", []) or []),
                        edges=tuple(getattr(raw, "edges", []) or []),
                        total_cost=float(getattr(raw, "total_cost", 0.0)),
                        optimized_cost=float(getattr(raw, "optimized_cost", getattr(raw, "total_cost", 0.0))),
                        total_time=float(getattr(raw, "total_time", 0.0)),
                        total_risk=float(getattr(raw, "total_risk", 0.0)),
                        w_survival=w_surv,
                        w_expected_cost=w_exp,
                    )
                )
            except Exception:
                LOGGER.exception("Invalid RawSolution structure for label; skipping.")
                continue

        return cls(solutions=sols)

    def _extremes(self) -> Optional[Dict[str, float]]:
        if not self.solutions:
            return None
        min_surv = min(s.w_survival for s in self.solutions)
        max_surv = max(s.w_survival for s in self.solutions)
        min_cost = min(s.w_expected_cost for s in self.solutions)
        max_cost = max(s.w_expected_cost for s in self.solutions)
        return {"min_surv": min_surv, "max_surv": max_surv, "min_cost": min_cost, "max_cost": max_cost}

    def extract_tank(self) -> Optional[ParetoSolution]:
        """El Tanque: mínimo absoluto en el eje de supervivencia (w_survival)."""
        if not self.solutions:
            return None
        return min(self.solutions, key=lambda s: s.w_survival)

    def extract_gambler(self) -> Optional[ParetoSolution]:
        """El Apostador: mínimo absoluto en el eje de costo esperado (w_expected_cost)."""
        if not self.solutions:
            return None
        return min(self.solutions, key=lambda s: s.w_expected_cost)

    def extract_tightrope(self) -> Optional[ParetoSolution]:
        """
        El Equilibrista: normaliza ambos ejes (w_survival, w_expected_cost) usando
        los extremos de la propia frontera y devuelve la solución con mínima distancia
        euclidiana al origen (utópico).
        """
        if not self.solutions:
            return None
        extremes = self._extremes()
        if extremes is None:
            return None

        min_s, max_s = extremes["min_surv"], extremes["max_surv"]
        min_c, max_c = extremes["min_cost"], extremes["max_cost"]

        def norm(value: float, vmin: float, vmax: float) -> float:
            if vmax <= vmin:
                return 0.0
            return (value - vmin) / (vmax - vmin)

        best = None
        best_dist = math.inf
        for s in self.solutions:
            ns = norm(s.w_survival, min_s, max_s)
            nc = norm(s.w_expected_cost, min_c, max_c)
            dist = math.hypot(ns, nc)
            if dist < best_dist:
                best_dist = dist
                best = s
        return best

    def extract_unicorn(self, overcost_threshold: float = 0.25) -> Optional[ParetoSolution]:
        """
        El Unicornio: regla de negocio condicional.
        Calcula el sobrecosto porcentual del Tanque frente al Apostador:
            overcost = (tank.total_cost - gambler.total_cost) / gambler.total_cost
        Si overcost >= overcost_threshold se considera Unicornio y se devuelve la solución
        que representa la anomalía (por defecto el Tanque). Si no, devuelve None.
        """
        tank = self.extract_tank()
        gambler = self.extract_gambler()
        if tank is None or gambler is None:
            return None
        try:
            if float(gambler.total_cost) == 0.0:
                return None
            overcost = (float(tank.total_cost) - float(gambler.total_cost)) / float(gambler.total_cost)
        except Exception:
            LOGGER.exception("Error calculando overcost for unicorn detection.")
            return None
        if overcost >= overcost_threshold:
            return tank
        return None

    def to_audit(self) -> Dict[str, Any]:
        """Resumen compacto para auditoría externa."""
        return {
            "n_solutions": len(self.solutions),
            "has_tank": self.extract_tank() is not None,
            "has_gambler": self.extract_gambler() is not None,
            "has_tightrope": self.extract_tightrope() is not None,
            "has_unicorn": self.extract_unicorn() is not None,
        }

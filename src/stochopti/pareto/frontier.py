"""stochopti/pareto/frontier.py — Abstract Pareto Frontier Reconstruction."""

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Dict, Any

from stochopti.core.types import PathSolution

LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class ParetoSolution:
    """Inmutable: representación de una solución en la frontera."""
    path: Sequence[str]
    edges: Sequence[str]
    objective_values: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": list(self.path),
            "edges": list(self.edges),
            "objective_values": dict(self.objective_values),
        }

@dataclass
class ParetoFrontier:
    """Frontera de Pareto abstracta con extractores de arquetipos agnósticos."""
    solutions: List[ParetoSolution] = field(default_factory=list)

    @classmethod
    def from_solver_results(cls, labels: Sequence, engine: Any) -> "ParetoFrontier":
        """Reconstruye la frontera desde las etiquetas producidas por el solver."""
        sols: List[ParetoSolution] = []
        for lbl in labels or []:
            try:
                raw: PathSolution = engine.reconstruct_path(lbl)
            except Exception as exc:
                LOGGER.exception("Failed to reconstruct PathSolution from label: %s", exc)
                continue
                
            try:
                sols.append(
                    ParetoSolution(
                        path=tuple(raw.path),
                        edges=tuple(raw.edges),
                        objective_values=dict(raw.objective_values)
                    )
                )
            except Exception:
                LOGGER.exception("Invalid PathSolution structure for label; skipping.")
                continue

        return cls(solutions=sols)

    def _extremes(self, obj1: str, obj2: str) -> Optional[Dict[str, float]]:
        """Calcula los valores extremos en la frontera para dos objetivos."""
        if not self.solutions:
            return None
        min_1 = min(s.objective_values.get(obj1, 0.0) for s in self.solutions)
        max_1 = max(s.objective_values.get(obj1, 0.0) for s in self.solutions)
        min_2 = min(s.objective_values.get(obj2, 0.0) for s in self.solutions)
        max_2 = max(s.objective_values.get(obj2, 0.0) for s in self.solutions)
        return {"min_1": min_1, "max_1": max_1, "min_2": min_2, "max_2": max_2}

    def extract_min_objective_1(self, obj1_name: str) -> Optional[ParetoSolution]:
        """El mínimo absoluto para el primer objetivo."""
        if not self.solutions:
            return None
        return min(self.solutions, key=lambda s: s.objective_values.get(obj1_name, math.inf))

    def extract_min_objective_2(self, obj2_name: str) -> Optional[ParetoSolution]:
        """El mínimo absoluto para el segundo objetivo."""
        if not self.solutions:
            return None
        return min(self.solutions, key=lambda s: s.objective_values.get(obj2_name, math.inf))

    def extract_utopian_closest(self, obj1: str, obj2: str) -> Optional[ParetoSolution]:
        """
        Calcula la solución más cercana al punto utópico ideal usando 
        distancia euclidiana sobre ejes normalizados (min-max escalar).
        """
        if not self.solutions:
            return None
        extremes = self._extremes(obj1, obj2)
        if extremes is None:
            return None

        min_1, max_1 = extremes["min_1"], extremes["max_1"]
        min_2, max_2 = extremes["min_2"], extremes["max_2"]

        def norm(value: float, vmin: float, vmax: float) -> float:
            if vmax <= vmin:
                return 0.0
            return (value - vmin) / (vmax - vmin)

        best = None
        best_dist = math.inf
        for s in self.solutions:
            n1 = norm(s.objective_values.get(obj1, 0.0), min_1, max_1)
            n2 = norm(s.objective_values.get(obj2, 0.0), min_2, max_2)
            dist = math.hypot(n1, n2)
            if dist < best_dist:
                best_dist = dist
                best = s
        return best

    def extract_pareto_anomaly(
        self, obj_base: str, obj_premium: str, overcost_threshold: float = 0.25
    ) -> Optional[ParetoSolution]:
        """
        Detecta anomalías estructurales comparando la solución óptima en el 
        objetivo base frente a la óptima en el objetivo premium.
        Si la diferencia relativa sobrepasa un umbral, se considera una anomalía de valor.
        """
        best_premium = self.extract_min_objective_1(obj_premium)
        best_base = self.extract_min_objective_2(obj_base)
        
        if best_premium is None or best_base is None:
            return None
            
        try:
            val_base = best_base.objective_values.get(obj_base, 0.0)
            val_premium = best_premium.objective_values.get(obj_base, 0.0)
            if val_base == 0.0:
                return None
            overcost = (val_premium - val_base) / val_base
        except Exception:
            LOGGER.exception("Error calculando overcost para anomalía de Pareto.")
            return None
            
        if overcost >= overcost_threshold:
            return best_premium
        return None

    def to_audit(self) -> Dict[str, Any]:
        """Auditoría agnóstica de la frontera generada."""
        return {
            "n_solutions": len(self.solutions)
        }

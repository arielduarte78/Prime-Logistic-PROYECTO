"""stochopti/pareto/solution.py — Estructuras de Soluciones y Perfiles."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Set

from stochopti.core.types import PathSolution

class SolutionTag(str, Enum):
    """Etiquetas estratégicas agnósticas (reemplazo de StrategicTag)."""
    LOW_COST = "LOW_COST"
    HIGH_RESILIENCE = "HIGH_RESILIENCE"
    BALANCED = "BALANCED"
    DISTRIBUTED_RISK = "DISTRIBUTED_RISK"
    SUBOPTIMAL = "SUBOPTIMAL"

@dataclass(frozen=True)
class RouteProfile:
    """Perfil estructural de una ruta en la red."""
    risk_scale: float
    entropy: float
    rigidity: float
    redundancy_index: float
    sensitivity_vector: Dict[str, float]

@dataclass(frozen=True)
class ScoredOption:
    """Opcón puntuada lista para ser recomendada."""
    solution: PathSolution
    profile: RouteProfile
    tags: Set[SolutionTag]
    recommendation_strength: float

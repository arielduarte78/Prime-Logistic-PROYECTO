"""stochopti/core/protocols.py — Interfaces de inyección de dependencia abstractas."""

from typing import Protocol, runtime_checkable, Any, Tuple, Dict
from stochopti.core.types import EdgeSpec, BetaPrior

@runtime_checkable
class EdgeCostFunction(Protocol):
    """
    Función inyectada por el usuario para calcular el costo escalar
    de una arista dados los pesos de la escalarización.
    """
    def __call__(self, edge: EdgeSpec, scalarization_weights: Dict[str, float]) -> float:
        ...

@runtime_checkable
class PriorProvider(Protocol):
    """
    Proveedor inyectado por el usuario para obtener los priors bayesianos
    iniciales de las aristas del grafo.
    """
    def get_priors(self) -> Dict[Tuple[str, str], BetaPrior]:
        ...

@runtime_checkable
class ThreatProvider(Protocol):
    """
    Proveedor inyectado para obtener factores de amenaza externos que
    degradan la confianza en las aristas. Retorna un factor entre 0 y 1.
    """
    def get_threat_level(self, edge: EdgeSpec) -> float:
        ...

@runtime_checkable
class ScenarioClassifier(Protocol):
    """
    Clasificador inyectado para determinar el éxito o fracaso de un
    escenario estocástico de Monte Carlo.
    """
    def classify(self, scenario: Dict[str, Any]) -> Tuple[bool, Tuple[str, ...]]:
        ...

import copy
import numpy as np
import random
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, field

from bloque2.incidents import (
    Manifest, 
    IncidentDefinition,
    Category,
    TargetType,
    AdjacencyAction
)

# ============================================================================
# ESTRUCTURAS DE DATOS (SNAPSHOTS Y ESCENARIOS)
# ============================================================================

@dataclass
class NetworkSnapshot:
    """Instantánea de las matrices de la red perturbada."""
    A: np.ndarray
    C: np.ndarray
    T: np.ndarray
    K: np.ndarray
    D: np.ndarray
    nodes: List[str]
    meta: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def n_nodes(self) -> int:
        """Retorna el número total de nodos en la red."""
        return len(self.nodes)

def load_base_network_from_bloque1(topology_package: Dict[str, Any]) -> NetworkSnapshot:
    """
    Función de traducción: Mapea la exportación del Bloque 1 al formato
    requerido por el Bloque 2 (Motor Estocástico).
    """
    try:
        return NetworkSnapshot(
            A=topology_package['A'],
            C=topology_package['C'],
            T=topology_package['T'],
            K=topology_package['K'],
            D=topology_package['D'],
            nodes=topology_package['nodes'],
            meta=topology_package.get('meta', {})
        )
    except KeyError as e:
        raise KeyError(f"El paquete de topología no contiene el campo requerido: {e}")
    
@dataclass
class ScenarioEvent:
    """Ocurrencia de un incidente en una iteración."""
    code: str
    level: str
    p_effective: float
    amplification: float
    affected_indices: List[int] = field(default_factory=list)

@dataclass
class Scenario:
    """Resultado final de una 'mañana posible'."""
    scenario_id: int
    network: NetworkSnapshot
    events: List[ScenarioEvent]
    seed: int
    
    @property
    def total_events(self) -> int:
        """Número total de incidentes ocurridos."""
        return len(self.events)

    @property
    def has_cascades(self) -> bool:
        """Indica si hubo eventos con amplificación por cascada."""
        return any(e.amplification > 1.1 for e in self.events)

    def get_capacity_reduction(self) -> float:
        """Calcula la fracción de capacidad retenida [0, 1]."""
        baseline_capacity = np.sum(self.network.A)
        if baseline_capacity == 0:
            return 0.0
        return np.sum(self.network.K > 0) / baseline_capacity

# ============================================================================
# GENERADOR MONTE CARLO DINÁMICO
# ============================================================================

class MonteCarloGenerator:
    """Motor que decide qué pasa hoy y cuánto duele según el estrés."""

    def __init__(self, base_network: NetworkSnapshot, manifest: Manifest, seed: Optional[int] = None):
        self.base_network = base_network
        self.manifest = manifest
        self.seed = seed
        
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
            
        self.global_params = {
            'alpha': manifest.global_parameters.alpha,
            'beta': manifest.global_parameters.beta,
            'gamma': manifest.global_parameters.gamma,
            'max_multiplier': manifest.global_parameters.outlier_cap.max_multiplier
        }

    def generate_scenarios(
        self, 
        n_scenarios: int, 
        progress_callback: Optional[Callable[[int, int], None]] = None # <--- AGREGAR ESTO
    ) -> List[Scenario]:
        """
        Genera N variantes de la realidad basadas en el manifiesto.
        """
        scenarios = []
        for i in range(n_scenarios):
            # Ejecutar la simulación de un escenario
            scenario = self._generate_single_scenario(i)
            scenarios.append(scenario)
            
            # Si nos pasaron una función para reportar progreso, la llamamos
            if progress_callback:
                progress_callback(i + 1, n_scenarios)
                
        return scenarios

    def _generate_single_scenario(self, scenario_id: int) -> Scenario:
        """Orquesta la cascada estocástica en una sola iteración."""
        perturbed_network = copy.deepcopy(self.base_network)
        occurred_events: List[ScenarioEvent] = []
        active_event_codes: Set[str] = set()
        current_stress = 0.0 

        # Procesamiento en orden jerárquico estricto
        for level in [Category.SYSTEMIC, Category.TACTICAL, Category.MICRO]:
            incidents = self.manifest.get_incidents_by_level(level)
            
            for incident in incidents:
                # 1. Probabilidad efectiva (Dado cargado)
                p_eff = incident.effective_probability(list(active_event_codes))
                
                if random.random() < p_eff:
                    # 2. El evento se activa: Acumulamos estrés antes de medir daño
                    current_stress += incident.stress_weight
                    
                    # 3. Aplicamos efectos estructurales y métricos dinámicos
                    indices = self._apply_incident(perturbed_network, incident, current_stress)
                    
                    event = ScenarioEvent(
                        code=incident.code,
                        level=incident.level.value,
                        p_effective=p_eff,
                        amplification=p_eff / incident.p_base if incident.p_base > 0 else 1.0,
                        affected_indices=indices
                    )
                    occurred_events.append(event)
                    active_event_codes.add(incident.code)

        perturbed_network.meta['stress_index'] = current_stress
        
        return Scenario(
            scenario_id=scenario_id,
            network=perturbed_network,
            events=occurred_events,
            seed=(self.seed + scenario_id) if self.seed is not None else scenario_id
        )

    def _apply_incident(self, network: NetworkSnapshot, incident: IncidentDefinition, current_stress: float) -> List[int]:
        """Aplica la disrupción a las matrices de la red."""
        indices = self._get_affected_indices(network, incident)
        if not indices: 
            return []

        # Efectos Estructurales (Físicos)
        self._apply_structural_effects(network, incident, indices)
        
        # Efectos en Métricas (Dinámicos por Stress)
        self._apply_metric_impacts(network, incident, indices, current_stress)
        
        return indices

    def _get_affected_indices(self, network: NetworkSnapshot, incident: IncidentDefinition) -> List[int]:
        selector = incident.target.selector
        if incident.target.type == TargetType.NETWORK:
            return list(range(network.n_nodes))
        
        # Wildcard simple: coincidencia por prefijo (ej: WAREHOUSE_*)
        if selector.endswith("*"):
            prefix = selector[:-1]
            return [i for i, node_id in enumerate(network.nodes) if node_id.startswith(prefix)]
        
        return [i for i, node_id in enumerate(network.nodes) if node_id == selector]

    def _apply_structural_effects(self, network: NetworkSnapshot, incident: IncidentDefinition, indices: List[int]):
        effects = incident.structural_effects
        
        if effects.adjacency.action == AdjacencyAction.DISABLE:
            for idx in indices:
                network.A[idx, :] = False
                network.A[:, idx] = False
                network.K[idx, :] = 0
                network.K[:, idx] = 0
        
        if effects.capacity.modifier != 1.0:
            for idx in indices:
                network.K[idx, :] *= effects.capacity.modifier
                network.K[:, idx] *= effects.capacity.modifier

    def _apply_metric_impacts(self, network: NetworkSnapshot, incident: IncidentDefinition, indices: List[int], current_stress: float):
        for impact in incident.metric_impacts:
            # Fórmula Prime: Base * (1 + Sensibilidad * Stress_Index)
            multiplier = incident.get_impact_multiplier(impact.metric, current_stress, self.global_params)
            multiplier = min(multiplier, self.global_params['max_multiplier'])
            
            for idx in indices:
                if impact.metric == 'C':
                    network.C[idx, :] *= multiplier
                elif impact.metric == 'T':
                    network.T[idx, :] *= multiplier

class ScenarioAnalyzer:
    """Herramientas de análisis para conjuntos de escenarios."""
    
    @staticmethod
    def compute_statistics(scenarios: List[Scenario]) -> Dict[str, Any]:
        """Calcula estadísticas agregadas de la simulación."""
        n_scenarios = len(scenarios)
        event_frequencies = {}
        cascade_count = 0
        scenarios_with_events = 0
        avg_capacity_reduction = 0.0
        
        for scenario in scenarios:
            if scenario.total_events > 0:
                scenarios_with_events += 1
            if scenario.has_cascades:
                cascade_count += 1
            for event in scenario.events:
                event_frequencies[event.code] = event_frequencies.get(event.code, 0) + 1
            avg_capacity_reduction += scenario.get_capacity_reduction()
        
        avg_capacity_reduction /= n_scenarios
        return {
            'n_scenarios': n_scenarios,
            'scenarios_with_events': scenarios_with_events,
            'event_frequencies': event_frequencies,
            'cascade_count': cascade_count,
            'avg_capacity_retention': avg_capacity_reduction,
            'avg_capacity_loss': 1.0 - avg_capacity_reduction
        }

    @staticmethod
    def get_worst_case_scenario(scenarios: List[Scenario]) -> Scenario:
        """Retorna el escenario con mayor pérdida de capacidad."""
        return min(scenarios, key=lambda s: s.get_capacity_reduction())

    @staticmethod
    def get_best_case_scenario(scenarios: List[Scenario]) -> Scenario:
        """Retorna el escenario con menor pérdida de capacidad."""
        return max(scenarios, key=lambda s: s.get_capacity_reduction())
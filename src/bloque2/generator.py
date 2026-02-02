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
# 1. ESTRUCTURAS DE DATOS (Módulo 1 y Output [cite: 13, 312])
# ============================================================================

@dataclass
class NetworkSnapshot:
    """Instantánea de la pentada de matrices mutada[cite: 11, 312]."""
    A: np.ndarray
    C: np.ndarray
    T: np.ndarray
    K: np.ndarray
    D: np.ndarray
    nodes: List[str]
    meta: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

@dataclass
class ScenarioEvent:
    """Metadatos de trazabilidad de la cascada (causa-efecto)."""
    code: str
    level: str
    p_effective: float
    intensity_multiplier: float
    affected_indices: List[int]

@dataclass
class Scenario:
    """Objeto PossibleTomorrow con resultados de la iteración[cite: 13, 485]."""
    scenario_id: int
    network: NetworkSnapshot
    events: List[ScenarioEvent]
    stress_index: float
    seed: int

# ============================================================================
# 2. EVALUADOR: MUESTREADOR DE INTENSIDAD (Módulo 3 [cite: 10, 421])
# ============================================================================

class IntensityEvaluator:
    """
    Transforma eventos binarios en impactos cuantitativos.
    Aplica el modelo de impacto dinámico y el Cap de Outliers [cite: 423-424].
    """
    @staticmethod
    def calcular_multiplicador(base_multiplier: float, S: float, coef: float) -> float:
        """
        μ_eff = μ_base * (1 + αS) o (1 + γS) según el Word[cite: 139, 300, 437].
        Aplica la Regla del Mazo: V_final <= 5.0 * V_base.
        """
        # Desplazamiento de la media por estrés sistémico
        impacto_escalado = 1 + ((base_multiplier - 1) * (1 + coef * S))
        
        # Cap de Outliers: Ningún shock degrada la variable más de 5 veces 
        return min(impacto_escalado, 5.0)

# ============================================================================
# 3. GENERADOR MONTE CARLO (Módulo 2: Cerebro de Cascada [cite: 9, 390])
# ============================================================================

class MonteCarloGenerator:
    """
    Orquestador probabilístico jerárquico.
    Decide qué pasa hoy respetando el 'Dado Cargado'[cite: 9, 160, 392].
    """
    def __init__(self, base_network: NetworkSnapshot, manifest: Manifest, seed: Optional[int] = None):
        self.base_network = base_network
        self.manifest = manifest
        self.seed = seed
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

    def generate_scenarios(self, n_scenarios: int, progress_callback: Optional[Callable] = None) -> List[Scenario]:
        """Bucle controlador de Monte Carlo[cite: 12]."""
        return [self._generate_single_scenario(i, progress_callback) for i in range(n_scenarios)]

    def _generate_single_scenario(self, scenario_id: int, callback: Optional[Callable]) -> Scenario:
        """Propagación de estado y lanzamiento condicionado[cite: 157, 159]."""
        # Clonar la pentada base (Inmutabilidad [cite: 452])
        net = copy.deepcopy(self.base_network)
        active_codes: Set[str] = set()
        scenario_events: List[ScenarioEvent] = []
        S = 0.0

        # Orden Topológico: Sistémico -> Táctico -> Micro [cite: 4, 155]
        for level in [Category.SYSTEMIC, Category.TACTICAL, Category.MICRO]:
            for incident in self.manifest.get_incidents_by_level(level):
                
                # Lógica de Dado Cargado: P_eff = P_base * Multiplicador_Influencia [cite: 20-22, 162, 413]
                p_eff = incident.effective_probability(list(active_codes))
                
                if random.random() < p_eff:
                    # El evento se activa
                    active_codes.add(incident.code)
                    # S = Σ w_k * 1{S_k activo} [cite: 133, 410]
                    S += incident.stress_weight
                    
                    # El ACTOR (Cirujano) aplica los cambios [cite: 11, 448]
                    indices = self._apply_to_matrices(net, incident, S)
                    
                    scenario_events.append(ScenarioEvent(
                        code=incident.code, level=level.value,
                        p_effective=p_eff, intensity_multiplier=1.0, # Simplificado para trazabilidad
                        affected_indices=indices
                    ))

        if callback: 
            callback(scenario_id + 1, 1000) # Ejemplo de callback
        return Scenario(scenario_id, net, scenario_events, S, (self.seed or 0) + scenario_id)

    def _apply_to_matrices(self, net: NetworkSnapshot, incident: IncidentDefinition, S: float) -> List[int]:
        """Aplica las Reglas de Oro del Actor [cite: 309-311, 460-464]."""
        indices = self._get_target_indices(net, incident)
        
        # 1. Kill-switch (Prevalencia de A): Si el camino muere, A=0 [cite: 310, 462]
        if incident.structural_effects.adjacency.action == AdjacencyAction.DISABLE:
            for idx in indices:
                net.A[idx, :], net.A[:, idx] = False, False
                net.K[idx, :], net.K[:, idx] = 0, 0

        # 2. Capacidad Conservadora: K solo cambia por sistémicos [cite: 311, 463]
        if incident.level == Category.SYSTEMIC and incident.structural_effects.capacity.modifier != 1.0:
            for idx in indices:
                net.K[idx, :] *= incident.structural_effects.capacity.modifier

        # 3. Multiplicatividad en T y C (Muestreo del Evaluador) [cite: 309, 461]
        for impact in incident.metric_impacts:
            # Seleccionar alfa (T) o gamma (C) según el Word [cite: 145, 300]
            coef = self.manifest.global_parameters.alpha if impact.metric == 'T' else self.manifest.global_parameters.gamma
            
            # El Evaluador calcula cuánto duele [cite: 421]
            multiplier = IntensityEvaluator.calcular_multiplicador(impact.base_multiplier, S, coef)
            
            for idx in indices:
                if impact.metric == 'T': 
                    net.T[idx, :] *= multiplier
                if impact.metric == 'C': 
                    net.C[idx, :] *= multiplier
                
        return indices

    def _get_target_indices(self, net: NetworkSnapshot, incident: IncidentDefinition) -> List[int]:
        """Selector de objetivos (NETWORK, NODE, ARC) [cite: 369-372]."""
        sel = incident.target.selector
        if incident.target.type == TargetType.NETWORK: 
            return list(range(net.n_nodes))
        return [i for i, node_id in enumerate(net.nodes) if node_id == sel or (sel.endswith("*") and node_id.startswith(sel[:-1]))]

# ============================================================================
# 4. ANALIZADOR DE RESILIENCIA (Stress Testing [cite: 106-114])
# ============================================================================

class ScenarioAnalyzer:
    @staticmethod
    def get_worst_case_scenario(scenarios: List[Scenario]) -> Scenario:
        """Identifica el escenario de colapso de red[cite: 111]."""
        return min(scenarios, key=lambda s: s.network.K.sum() if s.network.K.sum() > 0 else -s.stress_index)
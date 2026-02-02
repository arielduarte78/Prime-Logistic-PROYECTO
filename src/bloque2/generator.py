import copy
import numpy as np
import random
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from scipy.sparse import issparse

from bloque2.incidents import (
    Manifest, IncidentDefinition, Category, TargetType, AdjacencyAction
)

# ============================================================================
# 1. ESTRUCTURAS DE DATOS (Output y Snapshots)
# ============================================================================

@dataclass
class NetworkSnapshot:
    """Instantánea de la pentada de matrices mutada."""
    A: Any 
    C: Any
    T: Any
    K: Any
    D: Any
    nodes: List[str]
    meta: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def n_nodes(self) -> int: 
        return len(self.nodes)

@dataclass
class ScenarioEvent:
    """Metadatos de trazabilidad de la cascada."""
    code: str
    level: str
    p_effective: float
    intensity_multiplier: float
    affected_indices: List[int]

@dataclass
class Scenario:
    """Resultado final de una 'mañana posible'."""
    scenario_id: int
    network: NetworkSnapshot
    events: List[ScenarioEvent]
    stress_index: float
    seed: int

    def get_capacity_reduction(self) -> float:
        """
        Métrica de Resiliencia: Si K es infinito, mide conectividad por arcos (A).
        """
        # 1. Extraemos datos de K (Densa o Sparse)
        k_data = self.network.K.data if issparse(self.network.K) else self.network.K
        current_k = np.sum(k_data[np.isfinite(k_data)])
        
        base_k = self.network.meta.get('base_k_sum', 0.0)
        
        # 2. Si K es infinito o cero, usamos Conectividad Estructural (A) como fallback
        if base_k <= 0 or np.isinf(base_k):
            current_a = np.sum(self.network.A > 0)
            base_a = self.network.meta.get('base_a_sum', current_a)
            return float(current_a / base_a) if base_a > 0 else 0.0
            
        return float(current_k / base_k)

# ============================================================================
# 2. EVALUADOR E INTENSIDAD (Módulo 3)
# ============================================================================

class IntensityEvaluator:
    @staticmethod
    def calcular_multiplicador(base_multiplier: float, S: float, coef: float) -> float:
        """μ_eff = μ_base * (1 + αS). Cap de 5x."""
        impacto = 1 + ((base_multiplier - 1) * (1 + coef * S))
        return min(impacto, 5.0)

# ============================================================================
# 3. ACTOR: MUTADOR MATRICIAL (Módulo 4)
# ============================================================================

class NetworkActor:
    @staticmethod
    def apply_incident(net: NetworkSnapshot, incident: IncidentDefinition, indices: List[int], S: float, params: Any) -> float:
        m = 1.0
        
        # 1. Kill-switch (A y K)
        if incident.structural_effects.adjacency.action == AdjacencyAction.DISABLE:
            if issparse(net.A):
                net.A = net.A.tolil()
                net.K = net.K.tolil()
            
            for idx in indices:
                net.A[idx, :], net.A[:, idx] = 0, 0
                net.K[idx, :], net.K[:, idx] = 0, 0
            
            if not isinstance(net.A, np.ndarray):
                net.A = net.A.tocsr()
                net.K = net.K.tocsr()

        # 2. Capacidad (Solo si es Sistémico)
        if incident.level == Category.SYSTEMIC and incident.structural_effects.capacity.modifier != 1.0:
            for idx in indices:
                if issparse(net.K):
                    net.K.data[net.K.indptr[idx]:net.K.indptr[idx+1]] *= incident.structural_effects.capacity.modifier
                else:
                    net.K[idx, :] *= incident.structural_effects.capacity.modifier

        # 3. Métricas (C, T, D)
        for impact in incident.metric_impacts:
            coef = params.alpha if impact.metric == 'T' else params.gamma
            m = IntensityEvaluator.calcular_multiplicador(impact.base_multiplier, S, coef)
            
            target_matrix = getattr(net, impact.metric)
            for idx in indices:
                if issparse(target_matrix):
                    target_matrix.data[target_matrix.indptr[idx]:target_matrix.indptr[idx+1]] *= m
                else:
                    target_matrix[idx, :] *= m
        return m

# ============================================================================
# 4. GENERADOR Y ENGINE (Módulo 2 y 5)
# ============================================================================

class MonteCarloGenerator:
    def __init__(self, base_network: NetworkSnapshot, manifest: Manifest, seed: Optional[int] = None):
        self.base_network = base_network
        self.manifest = manifest
        self.seed = seed

    def _generate_single_scenario(self, scenario_id: int) -> Scenario:
        net = copy.deepcopy(self.base_network)
        active_codes, events, S = set(), [], 0.0
        
        for level in [Category.SYSTEMIC, Category.TACTICAL, Category.MICRO]:
            for inc in self.manifest.get_incidents_by_level(level):
                p_eff = inc.effective_probability(list(active_codes))
                if random.random() < p_eff:
                    active_codes.add(inc.code)
                    S += inc.stress_weight
                    indices = self._get_target_indices(net, inc)
                    m = NetworkActor.apply_incident(net, inc, indices, S, self.manifest.global_parameters)
                    events.append(ScenarioEvent(inc.code, level.value, p_eff, m, indices))
                    
        return Scenario(scenario_id, net, events, S, (self.seed or 0) + scenario_id)

    def _get_target_indices(self, net: NetworkSnapshot, inc: IncidentDefinition) -> List[int]:
        sel = inc.target.selector
        if inc.target.type == TargetType.NETWORK:
            return list(range(net.n_nodes))
        return [i for i, node in enumerate(net.nodes) if node == sel or (sel.endswith("*") and node.startswith(sel[:-1]))]

class MonteCarloEngine:
    def __init__(self, generator: MonteCarloGenerator):
        self.generator = generator

    def run(self, e_limit=0.01, window=50, max_iter=500):
        history, results = [], []
        for i in range(1, max_iter + 1):
            s = self.generator._generate_single_scenario(i)
            results.append(s)
            history.append(s.get_capacity_reduction())
            
            if i >= window * 2 and i % window == 0:
                if self._ha_convergido(history, window, e_limit):
                    print(f"✓ Convergencia alcanzada en {i} iteraciones.")
                    break
        return results

    def _ha_convergido(self, h, w, eps):
        prev, curr = h[-w*2 : -w], h[-w:]
        return abs(np.mean(curr) - np.mean(prev)) < eps and abs(np.var(curr) - np.var(prev)) < eps

# ============================================================================
# 5. ADAPTERS Y ANALYZER
# ============================================================================

def load_base_network_from_bloque1(topology_package: Dict[str, Any]) -> NetworkSnapshot:
    K_base = topology_package['K']
    A_base = topology_package['A']
    
    def sum_finite(m):
        data = m.data if issparse(m) else m
        finitos = data[np.isfinite(data)]
        return np.sum(finitos) if finitos.size > 0 else 0.0

    meta = topology_package.get('meta', {}).copy()
    meta['base_k_sum'] = sum_finite(K_base)
    meta['base_a_sum'] = np.sum(A_base > 0)

    return NetworkSnapshot(
        A=A_base, C=topology_package['C'], T=topology_package['T'],
        K=K_base, D=topology_package['D'], nodes=topology_package['nodes'], meta=meta
    )

class ScenarioAnalyzer:
    @staticmethod
    def compute_statistics(scenarios: List[Scenario]) -> Dict[str, Any]:
        ret = [s.get_capacity_reduction() for s in scenarios]
        avg = np.mean(ret)
        return {
            'n_scenarios': len(scenarios),
            'scenarios_with_events': sum(1 for s in scenarios if s.events),
            'avg_capacity_retention': avg,
            'avg_capacity_loss': 1.0 - avg
        }

    @staticmethod
    def get_worst_case_scenario(scenarios: List[Scenario]) -> Scenario:
        return min(scenarios, key=lambda s: s.get_capacity_reduction())
#src/bloque2/generator.py
import numpy as np
import random
from typing import List, Dict, Any, Optional, Sequence
from dataclasses import dataclass, field
from scipy.sparse import issparse
import scipy.sparse as sp

from src.bloque2.incidents import (
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

    @property
    def amplification(self) -> float:
        """Alias para intensity_multiplier (compatibilidad con integration.py)."""
        return self.intensity_multiplier


@dataclass
class Scenario:
    """Resultado final de una 'mañana posible'."""
    scenario_id: int
    network: NetworkSnapshot
    events: List[ScenarioEvent]
    stress_index: float
    seed: int

    @property
    def total_events(self) -> int:
        """Número total de eventos aplicados en este escenario."""
        return len(self.events)

    @property
    def has_cascades(self) -> bool:
        """True si hubo más de un evento (cascada)."""
        return len(self.events) > 1

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
            base_a = float(self.network.meta.get('base_a_sum', current_a) or current_a)
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
    def apply_incident(net: NetworkSnapshot, incident: IncidentDefinition,
                       indices: List[int], S: float, params: Any) -> float:
        m = 1.0

        if not indices:
            return m

        # 1. Kill-switch (A y K) - Exclusivamente sobre .data (Zero Structural Mutation)
        if incident.structural_effects.adjacency.action == AdjacencyAction.DISABLE:
            if issparse(net.A):
                n = net.A.shape[0]
                
                # SIMD Mask para inhabilitar destinos (entrantes)
                disabled_mask = np.zeros(n, dtype=bool)
                disabled_mask[indices] = True
                
                in_mask_A = disabled_mask[net.A.indices]
                net.A.data[in_mask_A] = 0.0
                
                in_mask_K = disabled_mask[net.K.indices]
                net.K.data[in_mask_K] = 0.0
                
                # Inhabilitar orígenes (salientes) recorriendo CSR indptr
                for idx in indices:
                    start_A, end_A = net.A.indptr[idx], net.A.indptr[idx + 1]
                    net.A.data[start_A:end_A] = 0.0
                    
                    start_K, end_K = net.K.indptr[idx], net.K.indptr[idx + 1]
                    net.K.data[start_K:end_K] = 0.0
            else:
                for idx in indices:
                    net.A[idx, :] = 0.0
                    net.A[:, idx] = 0.0
                    net.K[idx, :] = 0.0
                    net.K[:, idx] = 0.0

        # 2. Capacidad (Solo si es Sistémico)
        if (incident.level == Category.SYSTEMIC and
                incident.structural_effects.capacity.modifier != 1.0):
            mod = incident.structural_effects.capacity.modifier
            if issparse(net.K):
                for idx in indices:
                    net.K.data[net.K.indptr[idx]:net.K.indptr[idx + 1]] *= mod
            else:
                for idx in indices:
                    net.K[idx, :] *= mod

        # 3. Métricas (C, T, D)
        for impact in incident.metric_impacts:
            coef = params.alpha if impact.metric == 'T' else params.gamma
            m = IntensityEvaluator.calcular_multiplicador(impact.base_multiplier, S, coef)

            target_matrix = getattr(net, impact.metric)
            if issparse(target_matrix):
                for idx in indices:
                    target_matrix.data[target_matrix.indptr[idx]:target_matrix.indptr[idx + 1]] *= m
            else:
                for idx in indices:
                    target_matrix[idx, :] *= m
                    
        return m


# ============================================================================
# 4. GENERADOR Y ENGINE (Módulo 2 y 5)
# ============================================================================

class MonteCarloGenerator:
    def __init__(self, base_network: NetworkSnapshot, manifest: Manifest,
                 seed: Optional[int] = None):
        self.base_network = base_network
        self.manifest = manifest
        self.seed = seed

    def _generate_single_scenario(self, scenario_id: int) -> Scenario:
        net = NetworkSnapshot(
            A=self.base_network.A.copy(),
            C=self.base_network.C.copy(),
            T=self.base_network.T.copy(),
            K=self.base_network.K.copy(),
            D=self.base_network.D.copy(),
            nodes=self.base_network.nodes,
            meta=self.base_network.meta
        )
        active_codes, events = set(), []
        S_list: List[float] = [0.0]

        for level in [Category.SYSTEMIC, Category.TACTICAL, Category.MICRO]:
            for inc in self.manifest.get_incidents_by_level(level):
                p_eff = inc.effective_probability(list(active_codes))
                if random.random() < p_eff:
                    active_codes.add(inc.code)
                    S_list.append(inc.stress_weight)
                    current_S = sum(S_list)
                    indices = self._get_target_indices(net, inc)
                    m = NetworkActor.apply_incident(
                        net, inc, indices, current_S, self.manifest.global_parameters
                    )
                    events.append(ScenarioEvent(
                        inc.code, level.value, p_eff, m, indices
                    ))

        return Scenario(
            scenario_id, net, events, sum(S_list), (self.seed or 0) + scenario_id
        )

    def _simulate_events_only(self) -> List[IncidentDefinition]:
        active_codes, triggered = set(), []
        for level in [Category.SYSTEMIC, Category.TACTICAL, Category.MICRO]:
            for inc in self.manifest.get_incidents_by_level(level):
                p_eff = inc.effective_probability(list(active_codes))
                if random.random() < p_eff:
                    active_codes.add(inc.code)
                    triggered.append(inc)
        return triggered

    def _get_target_indices(self, net: NetworkSnapshot,
                            inc: IncidentDefinition) -> List[int]:
        sel = inc.target.selector
        if inc.target.type == TargetType.NETWORK:
            return list(range(net.n_nodes))
        return [
            i for i, node in enumerate(net.nodes)
            if node == sel or (sel.endswith("*") and node.startswith(sel[:-1]))
        ]


class MonteCarloEngine:
    def __init__(self, generator: MonteCarloGenerator):
        self.generator = generator

    def run(self, e_limit=0.0001, window=50, max_iter=5000):
        history, results = [], []
        for i in range(1, max_iter + 1):
            # 1. Generamos el escenario pesado
            s_obj = self.generator._generate_single_scenario(i)

            # 2. CALCULAMOS LAS MÉTRICAS ANTES DE BORRAR LA RED
            retention = s_obj.get_capacity_reduction()

            # 3. CREAMOS EL DICCIONARIO LIVIANO (Lo que el Auditor.py espera)
            #    PRESERVAMOS la topología completa para que Bloque 3 pueda
            #    mapear las perturbaciones estocásticas a aristas concretas.
            s_lite = {
                "scenario_id": str(s_obj.scenario_id),
                "capacity_retained": retention,
                "stress_index": s_obj.stress_index,
                "events": [
                    {
                        "code": e.code,
                        "level": e.level,
                        "p_effective": e.p_effective,
                        "intensity_multiplier": e.intensity_multiplier,
                        "affected_indices": list(e.affected_indices),
                    }
                    for e in s_obj.events
                ],
                "total_cost": 10.80,
                "base_cost": 10.00,
            }

            results.append(s_lite)
            history.append(retention)

            # Lógica de convergencia...
            if i >= window * 2 and i % window == 0:
                if self._ha_convergido(history, window, eps=e_limit):
                    print(f"[OK] Convergencia alcanzada en {i} iteraciones.")
                    break
        return results

    def run_by_zone(self, zone_event_map: Dict[str, List[str]], e_limit=0.001, window=100, max_iter=5000) -> Dict[str, float]:
        """
        No muta matrices. Calcula el stress escalar por zona y escenario.
        zone_event_map: dict {h3_res4: [code1, code2...]}
        Retorna: dict {h3_res4: avg_stress}
        """
        history = {z: [] for z in zone_event_map.keys()}
        
        for i in range(1, max_iter + 1):
            active_events = self.generator._simulate_events_only()
            
            for z, valid_codes in zone_event_map.items():
                cap = 1.0
                for inc in active_events:
                    if inc.code in valid_codes:
                        if inc.structural_effects.adjacency.action == AdjacencyAction.DISABLE:
                            cap *= 0.0
                        else:
                            cap *= inc.structural_effects.capacity.modifier
                history[z].append(cap)
                
            if i >= window * 2 and i % window == 0:
                all_converged = True
                for z in zone_event_map.keys():
                    if not self._ha_convergido(history[z], window, eps=e_limit):
                        all_converged = False
                        break
                if all_converged:
                    print(f"[OK] Convergencia zonal alcanzada en {i} iteraciones.")
                    break
                    
        return {z: float(1.0 - np.mean(history[z])) for z in zone_event_map.keys()}

    def _ha_convergido(self, h, w, eps):
        prev, curr = h[-w * 2: -w], h[-w:]
        return (abs(np.mean(curr) - np.mean(prev)) < eps and
                abs(np.var(curr) - np.var(prev)) < eps)


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
        A=A_base,
        C=topology_package['C'],
        T=topology_package['T'],
        K=K_base,
        D=topology_package['D'],
        nodes=topology_package['nodes'],
        meta=meta
    )


class ScenarioAnalyzer:
    @staticmethod
    def compute_statistics(scenarios: Sequence[Any]) -> Dict[str, Any]:
        # CAMBIO: Leemos la llave del diccionario en vez de llamar al método
        ret = [s['capacity_retained'] for s in scenarios]
        avg = np.mean(ret)
        return {
            'n_scenarios': len(scenarios),
            'scenarios_with_events': sum(1 for s in scenarios if s.get('events')),
            'avg_capacity_retention': avg,
            'avg_capacity_loss': 1.0 - avg
        }

    @staticmethod
    def get_worst_case_scenario(scenarios: Sequence[Any]) -> Any:
        # CAMBIO: Usamos la llave para encontrar el peor caso
        return min(scenarios, key=lambda s: s['capacity_retained'])

    @staticmethod
    def get_best_case_scenario(scenarios: Sequence[Any]) -> Any:
        """Retorna el escenario con mayor retención de capacidad."""
        return max(scenarios, key=lambda s: s['capacity_retained'])
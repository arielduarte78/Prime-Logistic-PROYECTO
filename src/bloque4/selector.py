#selector.py
from __future__ import annotations
import numpy as np
from typing import List, Set
from .schema import OptimizerConfig, RawSolution, RouteProfile, StrategicOption, StrategicTag

def select_strategic_options(
    solutions: List[RawSolution],
    profiles: List[RouteProfile],
    config: OptimizerConfig,
) -> List[StrategicOption]:
    """
    Orquestador de Decisiones: Filtra por Pareto y clasifica perfiles estratégicos
    utilizando los umbrales y pesos definidos en OptimizerConfig.
    """
    if not solutions:
        return []

    # 1. Vectorización de criterios (O(N) para preparar el terreno)
    costs = np.array([s.total_cost for s in solutions])
    risks = np.array([p.rigidity for p in profiles])
    # Invertimos entropía: mayor entropía es mejor (más resiliencia distribuida)
    # Al invertirla, el algoritmo de Pareto puede tratarla como una minimización
    entropies = np.array([-p.entropy for p in profiles])

    # 2. Identificación de la Frontera de Pareto (Eficiencia Multiobjetivo)
    pareto_mask = _vectorized_pareto_front(costs, risks, entropies)
    
    # 3. Normalización Robusta para Scoring
    c_norm = _minmax_scale(costs)
    r_norm = _minmax_scale(risks)
    e_norm = _minmax_scale(-entropies) # Volvemos a la escala positiva para el score

    options: List[StrategicOption] = []
    for i in range(len(solutions)):
        # Clasificación programática usando los umbrales del CONFIG
        tags = _classify_strategy(i, c_norm, r_norm, e_norm, pareto_mask[i], config)
        
        # Cálculo de fuerza de recomendación usando los pesos del CONFIG
        strength = _calculate_prime_strength(i, c_norm, r_norm, e_norm, config, pareto_mask[i])
        
        options.append(StrategicOption(
            solution=solutions[i],
            profile=profiles[i],
            strategic_tags=tags,
            recommendation_strength=strength
        ))

    return options

def _vectorized_pareto_front(c: np.ndarray, r: np.ndarray, e: np.ndarray) -> np.ndarray:
    """
    Calcula soluciones no dominadas usando broadcasting de NumPy.
    Una solución x domina a y si es <= en todo y < en al menos uno.
    """
    data = np.stack((c, r, e), axis=1)
    n = data.shape[0]
    is_efficient = np.ones(n, dtype=bool)
    for i, val in enumerate(data):
        # ¿Existe alguna solución 'j' que sea mejor que la solución 'i'?
        better_than_i = np.all(data <= val, axis=1) & np.any(data < val, axis=1)
        if np.any(better_than_i):
            is_efficient[i] = False
    return is_efficient

def _classify_strategy(
    idx: int, c: np.ndarray, r: np.ndarray, e: np.ndarray, 
    is_pareto: bool, config: OptimizerConfig
) -> Set[StrategicTag]:
    """Asigna etiquetas estratégicas basadas en la proximidad a los ideales locales."""
    if not is_pareto:
        return {StrategicTag.SUBOPTIMAL}

    tags: Set[StrategicTag] = set()
    
    # Usamos los umbrales (thresholds) definidos en el OptimizerConfig
    # Si la solución está dentro del X% del mejor valor encontrado en el set actual
    if c[idx] <= np.min(c) * (1.0 + config.cost_threshold):
        tags.add(StrategicTag.LOW_COST)
    
    if r[idx] <= np.min(r) * (1.0 + config.rigidity_threshold):
        tags.add(StrategicTag.HIGH_RESILIENCE)
    
    if e[idx] >= np.max(e) * (1.0 - config.entropy_threshold):
        tags.add(StrategicTag.DISTRIBUTED_RISK)

    # Si es eficiente pero no destaca en ningún extremo, es un balance
    if not tags:
        tags.add(StrategicTag.BALANCED)

    return tags

def _calculate_prime_strength(
    idx: int, c: np.ndarray, r: np.ndarray, e: np.ndarray, 
    config: OptimizerConfig, is_pareto: bool
) -> float:
    """Calcula la confianza del sistema basada en la ponderación del usuario."""
    if not is_pareto:
        return 0.1 # Penalización severa por ineficiencia estructural

    # El score es la suma ponderada de las bondades (1-valor para minimizar)
    # Queremos: Bajo costo (1-c), Bajo riesgo (1-r), Alta entropía (e)
    score = (
        config.cost_weight * (1.0 - c[idx]) +
        config.risk_weight * (1.0 - r[idx]) +
        config.entropy_weight * e[idx]
    )
    
    total_weight = config.cost_weight + config.risk_weight + config.entropy_weight
    strength = score / total_weight if total_weight > 0 else 0.5
    
    return float(np.clip(strength, 0.0, 1.0))

def _minmax_scale(arr: np.ndarray) -> np.ndarray:
    """Normalización neutral para comparabilidad de dimensiones."""
    if arr.size == 0:
        return arr
    diff = np.max(arr) - np.min(arr)
    if diff == 0:
        return np.full_like(arr, 0.5)
    return (arr - np.min(arr)) / diff
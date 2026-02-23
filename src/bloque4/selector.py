# selector.py
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
    Orquestador de decisiones: filtra por Pareto y clasifica perfiles estratégicos.
    Funciona de forma defensiva ante formatos variados de 'solutions' y 'profiles'.
    """
    if not solutions:
        return []

    # Asegurar correspondencia de longitudes
    n = min(len(solutions), len(profiles))
    if n == 0:
        return []

    # 1. Vectorización de criterios (defensiva)
    # Extraer costos; si falta, usar 0.0
    costs = np.array([float(getattr(s, "total_cost", 0.0)) for s in solutions[:n]], dtype=float)

    # Rigidity (rigidez) se toma desde el profile.rigidity
    risks = np.array([float(getattr(p, "rigidity", 0.0)) for p in profiles[:n]], dtype=float)

    # Entropía: mayor es mejor. Para Pareto (minimización) invertimos con signo negativo.
    entropies = np.array([float(getattr(p, "entropy", 0.0)) for p in profiles[:n]], dtype=float)
    entropies_for_pareto = -entropies

    # 2. Identificación de la Frontera de Pareto
    pareto_mask = _vectorized_pareto_front(costs, risks, entropies_for_pareto)

    # 3. Normalización robusta para scoring (0..1)
    c_norm = _minmax_scale(costs)
    r_norm = _minmax_scale(risks)
    e_norm = _minmax_scale(entropies)  # entropies already positive (higher better)

    options: List[StrategicOption] = []
    for i in range(n):
        tags = _classify_strategy(i, c_norm, r_norm, e_norm, bool(pareto_mask[i]), config)
        strength = _calculate_prime_strength(i, c_norm, r_norm, e_norm, config, bool(pareto_mask[i]))

        options.append(StrategicOption(
            solution=solutions[i],
            profile=profiles[i],
            strategic_tags=tags,
            recommendation_strength=strength
        ))

    return options


def _vectorized_pareto_front(c: np.ndarray, r: np.ndarray, e: np.ndarray) -> np.ndarray:
    """
    Calcula soluciones no dominadas.
    Una solución j domina a i si j <= i en todas las dimensiones y < en al menos una.
    Implementación O(n^2) pero clara y robusta.
    """
    data = np.stack((c, r, e), axis=1)
    n = data.shape[0]
    is_efficient = np.ones(n, dtype=bool)

    for i in range(n):
        vi = data[i]
        # Comprobar si existe j != i que domine a i
        for j in range(n):
            if j == i:
                continue
            vj = data[j]
            if np.all(vj <= vi) and np.any(vj < vi):
                is_efficient[i] = False
                break

    return is_efficient


def _classify_strategy(
    idx: int, c: np.ndarray, r: np.ndarray, e: np.ndarray,
    is_pareto: bool, config: OptimizerConfig
) -> Set[StrategicTag]:
    """Asigna etiquetas estratégicas basadas en umbrales del config (defensivo)."""
    if not is_pareto:
        return {StrategicTag.SUBOPTIMAL}

    tags: Set[StrategicTag] = set()

    # Valores de referencia (mejores en el conjunto)
    best_c = float(np.min(c)) if c.size > 0 else 0.0
    best_r = float(np.min(r)) if r.size > 0 else 0.0
    best_e = float(np.max(e)) if e.size > 0 else 0.0

    # Umbrales defensivos: si el valor está dentro del X% del mejor
    if best_c > 0 and c[idx] <= best_c * (1.0 + getattr(config, "cost_threshold", 0.0)):
        tags.add(StrategicTag.LOW_COST)

    if best_r > 0 and r[idx] <= best_r * (1.0 + getattr(config, "rigidity_threshold", 0.0)):
        tags.add(StrategicTag.HIGH_RESILIENCE)

    if best_e > 0 and e[idx] >= best_e * (1.0 - getattr(config, "entropy_threshold", 0.0)):
        tags.add(StrategicTag.DISTRIBUTED_RISK)

    if not tags:
        tags.add(StrategicTag.BALANCED)

    return tags


def _calculate_prime_strength(
    idx: int, c: np.ndarray, r: np.ndarray, e: np.ndarray,
    config: OptimizerConfig, is_pareto: bool
) -> float:
    """Calcula la confianza del sistema basada en las ponderaciones del config."""
    if not is_pareto:
        return 0.1

    # Extraer pesos defensivamente
    cost_w = float(getattr(config, "cost_weight", 1.0))
    risk_w = float(getattr(config, "risk_weight", 1.0))
    entropy_w = float(getattr(config, "entropy_weight", 1.0))

    # Score: queremos minimizar c y r, maximizar e
    score = (
        cost_w * (1.0 - c[idx]) +
        risk_w * (1.0 - r[idx]) +
        entropy_w * e[idx]
    )

    total_weight = cost_w + risk_w + entropy_w
    strength = score / total_weight if total_weight > 0 else 0.5

    return float(np.clip(strength, 0.0, 1.0))


def _minmax_scale(arr: np.ndarray) -> np.ndarray:
    """Normalización neutral para comparabilidad de dimensiones."""
    if arr.size == 0:
        return arr
    mn = float(np.min(arr))
    mx = float(np.max(arr))
    diff = mx - mn
    if diff == 0:
        return np.full_like(arr, 0.5, dtype=float)
    return (arr - mn) / diff

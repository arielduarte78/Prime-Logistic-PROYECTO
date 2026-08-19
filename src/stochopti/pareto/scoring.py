"""stochopti/pareto/scoring.py — Etiquetado y Recomendación de Soluciones Pareto."""

from typing import List, Set

from stochopti.pareto.frontier import ParetoFrontier, ParetoSolution
from stochopti.pareto.solution import RouteProfile, ScoredOption, SolutionTag
from stochopti.core.types import PathSolution

def _build_profile_from_solution(sol: ParetoSolution, obj1_name: str, obj2_name: str) -> RouteProfile:
    obj1 = sol.objective_values.get(obj1_name, 0.0)
    obj2 = sol.objective_values.get(obj2_name, 0.0)
    
    entropy = float(min(1.0, (obj1 + obj2) / (1.0 + obj2) if obj2 != -1.0 else 0.0))
    rigidity = float(max(0.0, 1.0 - entropy))
    redundancy_index = float(max(0.0, 1.0 - obj1))
    
    return RouteProfile(
        risk_scale=obj1,
        entropy=entropy,
        rigidity=rigidity,
        redundancy_index=redundancy_index,
        sensitivity_vector={obj1_name: obj1, obj2_name: obj2}
    )

def _derive_tags(profile: RouteProfile, sol: ParetoSolution, obj1_name: str, obj2_name: str) -> Set[SolutionTag]:
    tags = set()
    obj1 = sol.objective_values.get(obj1_name, 0.0)
    obj2 = sol.objective_values.get(obj2_name, 0.0)
    
    # Heurística genérica; en la práctica el usuario ajustará estos umbrales
    if obj2 <= 1.0 * obj2: 
        tags.add(SolutionTag.LOW_COST)

    if obj1 <= 0.1 or profile.redundancy_index > 0.9:
        tags.add(SolutionTag.HIGH_RESILIENCE)

    if profile.entropy > 0.6:
        tags.add(SolutionTag.DISTRIBUTED_RISK)

    if not tags:
        tags.add(SolutionTag.BALANCED)
    return tags

def _score_recommendation(sol: ParetoSolution, profile: RouteProfile, obj1_name: str, obj2_name: str) -> float:
    obj1 = sol.objective_values.get(obj1_name, 0.0)
    obj2 = sol.objective_values.get(obj2_name, 0.0)
    
    c = 1.0 / (1.0 + obj2)
    r = 1.0 / (1.0 + obj1)
    e = float(profile.entropy)
    raw = 0.5 * c + 0.3 * r + 0.2 * (1.0 - abs(0.5 - e))
    return float(max(0.0, min(1.0, raw)))

def build_scored_options(
    frontier: ParetoFrontier, 
    obj1_name: str = "obj1", 
    obj2_name: str = "obj2"
) -> List[ScoredOption]:
    """Genera opciones puntuadas a partir de la frontera cruda."""
    options = []
    for sol in frontier.solutions:
        profile = _build_profile_from_solution(sol, obj1_name, obj2_name)
        tags = _derive_tags(profile, sol, obj1_name, obj2_name)
        strength = _score_recommendation(sol, profile, obj1_name, obj2_name)
        
        path_sol = PathSolution(
            path=list(sol.path),
            edges=list(sol.edges),
            objective_values=dict(sol.objective_values)
        )
        
        opt = ScoredOption(
            solution=path_sol,
            profile=profile,
            tags=tags,
            recommendation_strength=float(strength)
        )
        options.append(opt)
    return options

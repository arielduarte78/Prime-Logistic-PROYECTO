#profiler.py
from __future__ import annotations

from typing import  Dict,Tuple
import numpy as np
from .schema import Graph, OptimizerConfig, RawSolution, RouteProfile

def profile_route(
    graph: Graph,
    solution: RawSolution,
    config: OptimizerConfig,
) -> RouteProfile:
    """
    Analizador estructural de rutas. 
    Transforma una solución cruda en un perfil de riesgo y resiliencia.
    """
    if not solution.edges:
        return RouteProfile(0.0, 0.0, 1.0, 0.0, {})

    # 1. Preparación de datos vectoriales
    edges_in_route = [graph.edge_by_id(eid) for eid in solution.edges]
    risk_weights = np.array([e.risk_weight for e in edges_in_route if e.risk_weight is not None])
    
    # 2. Cálculo de métricas base
    scale = len(solution.edges) / len(graph.edges)
    entropy = _calculate_relative_entropy(risk_weights)
    
    # 3. Redundancia Real (Análisis de Grafo, no de lista)
    # Medimos qué tan "sola" está la ruta en el mapa
    ri = _calculate_real_redundancy(graph, solution, threshold=1.3)
    
    # 4. Rigidez (Sensibilidad al fallo crítico)
    # ¿Cuánto duele que se rompa el eslabón más débil?
    rigidity, sensitivity = _calculate_rigidity(graph, solution, config, ri)

    return RouteProfile(
        risk_scale=float(np.sum(risk_weights)),
        entropy=entropy,
        rigidity=rigidity,
        redundancy_index=ri,
        sensitivity_vector={
            "scale": scale,
            **sensitivity
        }
    )

def _calculate_relative_entropy(weights: np.ndarray) -> float:
    """Mide la concentración del riesgo (Incertidumbre de Shannon)."""
    if weights.size <= 1 or np.sum(weights) <= 0:
        return 0.0
    
    p = weights / np.sum(weights)
    # Filtramos ceros para evitar log(0)
    p = p[p > 0]
    h_abs = -np.sum(p * np.log2(p))
    
    # Normalizamos por el logaritmo del número de arcos (H_max)
    return float(h_abs / np.log2(weights.size))

def _calculate_real_redundancy(graph: Graph, solution: RawSolution, threshold: float) -> float:
    """
    Calcula el índice de redundancia estructural.
    RI = (Arcos con alternativa viable) / (Total arcos de la ruta)
    """
    # Construimos un set de búsqueda rápida para nodos de la ruta
    redundant_count = 0
    
    # Para cada arco de la ruta, vemos si hay un "bypass" en el grafo original
    for edge_id in solution.edges:
        edge = graph.edge_by_id(edge_id)
        # Buscamos si existe otro arco que conecte source -> target
        # o una combinación simple que no sea el arco actual.
        alternatives = [
            e for e in graph.edges 
            if e.source == edge.source and e.target == edge.target and e.edge_id != edge.edge_id
        ]
        
        if alternatives:
            # Si hay un arco paralelo con costo razonable, hay redundancia
            if any(alt.cost <= edge.cost * threshold for alt in alternatives):
                redundant_count += 1
                
    return redundant_count / len(solution.edges)

def _calculate_rigidity(
    graph: Graph, 
    solution: RawSolution, 
    config: OptimizerConfig,
    ri: float
) -> Tuple[float, Dict[str, float]]:
    """
    Calcula la rigidez como una combinación de vulnerabilidades.
    """
    # R_edge: Impacto del arco con mayor riesgo relativo
    edges_in_route = [graph.edge_by_id(eid) for eid in solution.edges]
    max_risk_edge = max(e.risk or 0.0 for e in edges_in_route)
    
    # R_node: Concentración de la ruta (¿Pasa por muchos nodos clave?)
    # Usamos el inverso de la escala como proxy de exposición
    node_exposure = 1.0 - (len(set(solution.path)) / len(graph.nodes))
    
    # R_cost: Variabilidad del costo
    costs = np.array([e.cost for e in edges_in_route])
    cost_volatility = np.std(costs) / np.mean(costs) if np.mean(costs) > 0 else 0.0
    
    # R_redundancy: La falta de opciones
    vulnerability = 1.0 - ri

    components = {
        "edge_risk_impact": float(max_risk_edge),
        "node_exposure": float(node_exposure),
        "cost_volatility": float(np.clip(cost_volatility, 0, 1)),
        "redundancy_vulnerability": float(vulnerability)
    }

    # Combinación lineal pesada según config
    weights = np.array(config.rigidity_weights)
    val_array = np.array([
        components["edge_risk_impact"],
        components["node_exposure"],
        components["cost_volatility"],
        components["redundancy_vulnerability"]
    ])
    
    rigidity = float(np.dot(weights, val_array))
    return rigidity, components
#src/block5/cost_matrix_builder.py
import math
import rustworkx as rx
from typing import List, Tuple, Any
from collections import OrderedDict
from src.block5.lambda_scalarizer import get_weight_function
from src.bloque1.graph_builder import EdgePayload
from src.block5.speed_profile_loader import get_h3_parent, get_velocity_multiplier

UNREACHABLE_PENALTY = 10 ** 13
MAX_TIME_MINUTES = 1440

# Cache LRU acotado para tiempos — independiente del arquetipo
# Clave: (id(payload), departure_hour) — el tiempo no depende del arquetipo
_MAX_TIME_CACHE_SIZE = 500_000
_time_weight_cache: OrderedDict = OrderedDict()

def _time_cache_set(key: tuple, value: float) -> None:
    if key in _time_weight_cache:
        _time_weight_cache.move_to_end(key)
    else:
        if len(_time_weight_cache) >= _MAX_TIME_CACHE_SIZE:
            _time_weight_cache.popitem(last=False)
    _time_weight_cache[key] = value

def clear_time_weight_cache() -> None:
    """Llamar al inicio de cada batch nocturno."""
    _time_weight_cache.clear()

def _get_time_weight_fn(cost_env: Any, departure_hour: int, speed_profiles: dict, osm_to_rx: dict = None, node_filter: set = None):
    """
    Weight function para Dijkstra temporal.
    No depende del arquetipo — hit rate máximo entre todos los archetypes
    del mismo request dado que departure_hour es igual para todos.
    """
    def time_weight(edge: Any) -> float:
        payload = edge if isinstance(edge, EdgePayload) else edge[2]

        if node_filter is not None and osm_to_rx is not None:
            v_rx = osm_to_rx.get(payload.v_osm)
            if v_rx not in node_filter:
                return math.inf

        cache_key = (id(payload), departure_hour)

        cached = _time_weight_cache.get(cache_key)
        if cached is not None:
            _time_weight_cache.move_to_end(cache_key)
            return cached

        dist_km = payload.length / 1000.0
        h3_parent = get_h3_parent(payload.h3_index)
        multiplier = get_velocity_multiplier(
            speed_profiles, payload.highway, h3_parent, departure_hour
        )
        effective_velocity = cost_env.velocidad_comercial_kmh * multiplier
        result = dist_km / effective_velocity if effective_velocity > 0 else math.inf

        _time_cache_set(cache_key, result)
        return result

    return time_weight


def build_time_matrix_only(
    graph: rx.PyDiGraph,
    nodes_of_interest: List[int],
    cost_env: Any,
    osm_to_rx: dict,
    departure_hour: int = 12,
    speed_profiles: dict = None,
    node_filter: set = None
) -> List[List[int]]:
    """
    Calcula únicamente la time_matrix. Llamar una vez por request
    antes del loop de arquetipos para evitar Dijkstra temporal redundante.
    """
    if speed_profiles is None:
        speed_profiles = {}

    time_fn = _get_time_weight_fn(cost_env, departure_hour, speed_profiles, osm_to_rx=osm_to_rx, node_filter=node_filter)
    n_size = len(nodes_of_interest)
    time_matrix: List[List[int]] = []

    for i in range(n_size):
        origin_node = nodes_of_interest[i]
        shortest_times = rx.dijkstra_shortest_path_lengths(
            graph, origin_node, edge_cost_fn=time_fn
        )
        time_row: List[int] = []
        for j in range(n_size):
            dest_node = nodes_of_interest[j]
            if origin_node == dest_node:
                time_row.append(0)
            else:
                raw_time = shortest_times[dest_node] if dest_node in shortest_times else math.inf
                time_row.append(
                    int(math.ceil(raw_time * 60)) if math.isfinite(raw_time) else MAX_TIME_MINUTES
                )
        time_matrix.append(time_row)

    return time_matrix

def build_dense_cost_matrix(
    graph: rx.PyDiGraph,
    nodes_of_interest: List[int],
    archetype: str,
    cost_env: Any,
    threat_matrix: dict,
    judge: Any,
    osm_to_rx: dict,
    departure_hour: int = 12,
    speed_profiles: dict = None,
    precomputed_time_matrix: List[List[int]] = None,
    node_filter: set = None,
    fallback_counter: list = None
) -> Tuple[List[List[int]], List[List[int]]]:
    """
    Retorna (cost_matrix, time_matrix).
    
    cost_matrix: costos financieros escalados ×100 para OR-Tools.
    time_matrix: tiempos de viaje en minutos enteros para dimensión CVRPTW.
    
    Ambas matrices se calculan en el mismo loop con dos Dijkstra por origen.
    El Dijkstra temporal tiene hit rate perfecto entre arquetipos del mismo
    request porque su cache no depende del arquetipo.
    """
    if speed_profiles is None:
        speed_profiles = {}

    weight_fn = get_weight_function(
        archetype, cost_env, threat_matrix, judge,
        osm_to_rx, departure_hour, speed_profiles,
        node_filter=node_filter,
        fallback_counter=fallback_counter
    )
    # Solo instanciar time_fn si vamos a usarlo
    time_fn = _get_time_weight_fn(cost_env, departure_hour, speed_profiles, osm_to_rx, node_filter) if precomputed_time_matrix is None else None

    n_size = len(nodes_of_interest)
    cost_matrix: List[List[int]] = []
    time_matrix: List[List[int]] = []

    for i in range(n_size):
        origin_node = nodes_of_interest[i]

        shortest_costs = rx.dijkstra_shortest_path_lengths(
            graph, origin_node, edge_cost_fn=weight_fn
        )
        
        # Dijkstra temporal: solo si no viene precalculado
        if precomputed_time_matrix is None:
            shortest_times = rx.dijkstra_shortest_path_lengths(
                graph, origin_node, edge_cost_fn=time_fn
            )

        cost_row: List[int] = []
        time_row: List[int] = []

        for j in range(n_size):
            dest_node = nodes_of_interest[j]
            if origin_node == dest_node:
                cost_row.append(0)
                time_row.append(0)
            else:
                raw_cost = shortest_costs[dest_node] if dest_node in shortest_costs else math.inf
                cost_row.append(
                    int(round(raw_cost * 100)) if math.isfinite(raw_cost) else UNREACHABLE_PENALTY
                )
                if precomputed_time_matrix is not None:
                    time_row.append(precomputed_time_matrix[i][j])
                else:
                    raw_time = shortest_times[dest_node] if dest_node in shortest_times else math.inf
                    time_row.append(
                        int(math.ceil(raw_time * 60)) if math.isfinite(raw_time) else MAX_TIME_MINUTES
                    )

        cost_matrix.append(cost_row)
        time_matrix.append(time_row)

    return cost_matrix, time_matrix if precomputed_time_matrix is None else precomputed_time_matrix

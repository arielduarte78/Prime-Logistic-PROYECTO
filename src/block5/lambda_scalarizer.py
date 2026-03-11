#src/block5/lambda_scalarizer.py
import math
from typing import Callable, Any
from functools import lru_cache
from collections import OrderedDict

from src.bloque1.graph_builder import EdgePayload
from src.block5.speed_profile_loader import get_h3_parent, get_velocity_multiplier
from src.bloque4.cost_calculator import compute_edge_cost

# Cache a nivel de módulo: sobrevive entre requests
# Clave: (id(payload), departure_hour, archetype)
# Los objetos cost_env/judge/threat_matrix/speed_profiles son singletons
# inmutables en app.state — no necesitan entrar en la clave
_MAX_CACHE_SIZE = 500_000
_cost_cache: OrderedDict = OrderedDict()

def _cache_get(key):
    if key in _cost_cache:
        _cost_cache.move_to_end(key)
        return _cost_cache[key], True
    return None, False

def _cache_set(key, value):
    if key in _cost_cache:
        _cost_cache.move_to_end(key)
    else:
        if len(_cost_cache) >= _MAX_CACHE_SIZE:
            _cost_cache.popitem(last=False)  # Evict LRU
    _cost_cache[key] = value

def get_weight_function(
    archetype: str,
    cost_env: Any,
    threat_matrix: dict,
    judge: Any,
    osm_to_rx: dict,
    departure_hour: int = 12,
    speed_profiles: dict = None,
    node_filter: set = None
) -> Callable[[Any], float]:
    if speed_profiles is None:
        speed_profiles = {}

    def weight_func(edge: Any) -> float:
        payload = edge if isinstance(edge, EdgePayload) else edge[2]

        v_rx = osm_to_rx.get(payload.v_osm)
        if node_filter is not None and v_rx not in node_filter:
            return math.inf

        cache_key = (id(payload), departure_hour, archetype)
        cached, hit = _cache_get(cache_key)
        if hit:
            return cached

        u_rx = osm_to_rx.get(payload.u_osm)

        result = compute_edge_cost(
            payload=payload,
            u_rx=u_rx,
            v_rx=v_rx,
            cost_env=cost_env,
            threat_matrix=threat_matrix,
            judge=judge,
            departure_hour=departure_hour,
            speed_profiles=speed_profiles,
            archetype=archetype
        )

        _cache_set(cache_key, result)
        return result

    return weight_func

def clear_cost_cache() -> None:
    """Llamar al inicio de cada batch nocturno para evitar stale data."""
    _cost_cache.clear()

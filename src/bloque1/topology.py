# src/bloque1/topology.py
import math
import logging
from typing import Dict, List, Any

import numpy as np

from .config import MODE_MAX_CAPACITY, MODE_FREQUENCY_WEIGHT, MODE_AVG_SPEED_KMH, TRUCK_ROUTE_MULTIPLIER, UNIT_CONVERSIONS_TO_TON

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0


class GeometryEngine:
    @staticmethod
    def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return EARTH_RADIUS_KM * c


class TopologyBuilder:
    def __init__(self, indexer):
        self.indexer = indexer
        self._adjacency: Dict[str, List[Any]] = {}
        self._distances: Dict[str, float] = {}
        self._node_order: List[str] = []
        self._built = False

    def build_topology(self) -> None:
        logger.info("Construyendo topología híbrida...")
        node_ids = list(self.indexer.get_all_node_ids())
        self._node_order = node_ids.copy()
        self._distances.clear()
        self._adjacency = {nid: [] for nid in self._node_order}

        for arc in self.indexer.iter_arcs():
            try:
                if not getattr(arc, "active", True):
                    continue
                origin = self.indexer.get_node(arc.origin)
                dest = self.indexer.get_node(arc.destination)
                if origin is None or dest is None:
                    logger.warning("Arc %s references missing node: %s -> %s",
                                   getattr(arc, "id", "<no-id>"), arc.origin, arc.destination)
                    continue
                dist = GeometryEngine.haversine(origin.lat, origin.lon, dest.lat, dest.lon)
                self._distances[arc.id] = dist
                self._adjacency.setdefault(origin.id, []).append(arc)
            except Exception:
                logger.exception("Error procesando arco %s", getattr(arc, "id", "<no-id>"))

        self._built = True
        logger.info("Topología finalizada. %d nodos indexados.", len(self._node_order))

    def export_matrices(self, sparse: bool = False) -> Dict[str, Any]:
        if not self._built:
            raise RuntimeError("Topology not built. Call build_topology() first.")

        n = len(self._node_order)
        idx_map = {nid: i for i, nid in enumerate(self._node_order)}

        mat_c = np.full((n, n), np.inf, dtype=np.float32)
        mat_t = np.full((n, n), np.inf, dtype=np.float32)
        mat_k = np.full((n, n), np.inf, dtype=np.float32)
        mat_a = np.zeros((n, n), dtype=np.bool_)

        for origin_id, arcs in self._adjacency.items():
            i = idx_map.get(origin_id)
            if i is None:
                continue
            for arc in arcs:
                j = idx_map.get(arc.destination)
                if j is None:
                    continue
                if not getattr(arc, "active", True):
                    continue

                mat_a[i, j] = True
                dist_km = self._distances.get(arc.id, None)
                if dist_km is None:
                    logger.debug("Distancia no calculada para arco %s; se omite", getattr(arc, "id", "<no-id>"))
                    continue

                var_coef = 1.0
                try:
                    if getattr(arc, "cost_profile", None) and getattr(arc.cost_profile, "params", None):
                        var_coef = arc.cost_profile.params.get("variable_coef", var_coef)
                except Exception:
                    logger.debug("No se pudo leer cost_profile de arco %s", getattr(arc, "id", "<no-id>"))
                mat_c[i, j] = float(dist_km) * float(var_coef)

                speed_def = None
                mode = None
                route_type = None
                try:
                    if getattr(arc, "speed_profile", None):
                        speed_def = getattr(arc.speed_profile, "default", None)
                except Exception:
                    speed_def = None

                md = getattr(arc, "metadata", None)
                if isinstance(md, dict):
                    mode = md.get("mode") or md.get("transport_type") or md.get("transport_mode")
                    route_type = md.get("route_type") or md.get("road_type")
                else:
                    extras = getattr(md, "extras", None)
                    if isinstance(extras, dict):
                        mode = extras.get("mode") or extras.get("transport_type") or extras.get("transport_mode")
                        route_type = extras.get("route_type") or extras.get("road_type")
                    else:
                        mode = getattr(md, "mode", None) or getattr(arc, "mode", None)
                        route_type = getattr(md, "route_type", None) or getattr(arc, "route_type", None)

                if speed_def is None:
                    if mode:
                        speed_def = MODE_AVG_SPEED_KMH.get(str(mode).strip().lower(), MODE_AVG_SPEED_KMH.get("default"))
                    else:
                        speed_def = MODE_AVG_SPEED_KMH.get("default")

                if mode and str(mode).strip().lower() in ("truck", "camion", "truck_trailer"):
                    if route_type:
                        mult = TRUCK_ROUTE_MULTIPLIER.get(str(route_type).strip().lower(), TRUCK_ROUTE_MULTIPLIER.get("default", 0.9))
                        speed_def = float(speed_def) * float(mult)

                if speed_def is None or speed_def <= 0:
                    mat_t[i, j] = np.inf
                else:
                    mat_t[i, j] = float(dist_km) / float(speed_def)

                cap_val = None
                cap_unit = None
                try:
                    cap_val = getattr(arc, "capacity", None)
                    if cap_val is None:
                        if isinstance(md, dict):
                            cap_val = md.get("capacity", None)
                            cap_unit = md.get("capacity_unit", None)
                        else:
                            extras = getattr(md, "extras", None)
                            if isinstance(extras, dict):
                                cap_val = extras.get("capacity", None)
                                cap_unit = extras.get("capacity_unit", None)
                            else:
                                cap_val = getattr(md, "capacity", None)
                                cap_unit = getattr(md, "capacity_unit", None)
                except Exception:
                    cap_val = None
                    cap_unit = None

                if cap_val is None:
                    mat_k[i, j] = np.inf
                else:
                    try:
                        cap_f = float(cap_val)
                    except Exception:
                        logger.warning("Arc %s capacity inválida '%s'; se marca como sin límite", getattr(arc, "id", "<no-id>"), cap_val)
                        mat_k[i, j] = np.inf
                        continue

                    if cap_unit:
                        conv = UNIT_CONVERSIONS_TO_TON.get(str(cap_unit).lower())
                        if conv is not None:
                            cap_f = cap_f * float(conv)
                        else:
                            logger.warning("Arc %s capacity_unit desconocida '%s'; se asume toneladas", getattr(arc, "id", "<no-id>"), cap_unit)

                    threshold = MODE_MAX_CAPACITY.get("default", 1e7)
                    if mode:
                        mode_key = str(mode).strip().lower()
                        threshold = MODE_MAX_CAPACITY.get(mode_key, threshold)

                    if cap_f < 0:
                        logger.warning("Arc %s tiene capacity negativa %s; se pone 0", getattr(arc, "id", "<no-id>"), cap_f)
                        mat_k[i, j] = 0.0
                    elif cap_f > threshold:
                        logger.warning("Arc %s capacity %s (ton) excede umbral para modo '%s' (%s ton); se clampa a %s",
                                       getattr(arc, "id", "<no-id>"), cap_f, mode or "unknown", threshold, threshold)
                        mat_k[i, j] = float(threshold)
                    else:
                        mat_k[i, j] = float(cap_f)

        vec_d = np.zeros(n, dtype=np.float32)
        for i, nid in enumerate(self._node_order):
            node = self.indexer.get_node(nid)
            if node:
                demand = float(getattr(node, "demand", 0.0) or 0.0)
                supply = float(getattr(node, "supply", 0.0) or 0.0)
                vec_d[i] = demand - supply

        meta = {
            "units": {
                "distance": "km",
                "cost": "currency_per_unit",
                "time": "hours",
                "capacity": "toneladas",
                "demand": "units"
            },
            "node_index": self._node_order.copy(),
            "mode_thresholds": MODE_MAX_CAPACITY.copy(),
            "mode_frequency": MODE_FREQUENCY_WEIGHT.copy(),
            "mode_avg_speed_kmh": MODE_AVG_SPEED_KMH.copy(),
            "truck_route_multiplier": TRUCK_ROUTE_MULTIPLIER.copy()
        }

        if sparse:
            try:
                from scipy.sparse import csr_matrix  # type: ignore
                sparse_A = csr_matrix(mat_a.astype(np.int8))
                sparse_C = csr_matrix(mat_c)
                sparse_T = csr_matrix(mat_t)
                sparse_K = csr_matrix(mat_k)
                return {
                    "nodes": self._node_order.copy(),
                    "A": sparse_A,
                    "C": sparse_C,
                    "T": sparse_T,
                    "K": sparse_K,
                    "D": vec_d,
                    "meta": meta
                }
            except Exception:
                logger.warning("scipy no disponible o conversión falló; devolviendo matrices densas")

        return {
            "nodes": self._node_order.copy(),
            "A": mat_a,
            "C": mat_c,
            "T": mat_t,
            "K": mat_k,
            "D": vec_d,
            "meta": meta
        }

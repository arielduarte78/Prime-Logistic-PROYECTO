# src/bloque1/topology.py
import logging
from typing import Dict, List, Any

import numpy as np
from scipy.sparse import csr_matrix

from .config import (
    MODE_MAX_CAPACITY,
    MODE_FREQUENCY_WEIGHT,
    MODE_AVG_SPEED_KMH,
    TRUCK_ROUTE_MULTIPLIER,
    UNIT_CONVERSIONS_TO_TON,
)

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0


def vectorized_haversine(lat1, lon1, lat2, lon2):
    """
    Calcula distancia entre arrays de coordenadas.
    Input: arrays numpy shape (N,)
    Output: array numpy shape (N,) con distancias en km.
    """
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)

    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


class TopologyBuilder:
    def __init__(self, indexer):
        self.indexer = indexer
        self._node_order: List[str] = []
        self._built = False

    def build_topology(self) -> None:
        logger.info("Construyendo topología...")
        self._node_order = list(self.indexer.get_all_node_ids())
        self._built = True
        logger.info("Topología finalizada. %d nodos indexados.", len(self._node_order))

    def export_matrices(self, sparse: bool = True) -> Dict[str, Any]:
        if not self._built:
            raise RuntimeError("Topology not built. Call build_topology() first.")

        n = len(self._node_order)
        idx_map = {nid: i for i, nid in enumerate(self._node_order)}

        # Arrays planos para COO
        rows, cols = [], []
        data_cost, data_time, data_cap = [], [], []

        lat_u, lon_u, lat_v, lon_v = [], [], [], []
        speeds, modes, route_types = [], [], []

        for arc in self.indexer.iter_arcs():
            if not getattr(arc, "active", True):
                continue
            origin = self.indexer.get_node(arc.origin)
            dest = self.indexer.get_node(arc.destination)
            if origin is None or dest is None:
                logger.warning("Arc %s references missing node: %s -> %s",
                               getattr(arc, "id", "<no-id>"), arc.origin, arc.destination)
                continue

            i, j = idx_map[origin.id], idx_map[dest.id]
            rows.append(i)
            cols.append(j)

            # Cost profile
            var_coef = 1.0
            if getattr(arc, "cost_profile", None) and getattr(arc.cost_profile, "params", None):
                var_coef = arc.cost_profile.params.get("variable_coef", var_coef)
            data_cost.append(var_coef)  # multiplicaremos luego por distancia

            # Speed profile
            speed_def = getattr(getattr(arc, "speed_profile", None), "default", None)
            md = getattr(arc, "metadata", None)
            mode, route_type = None, None
            if isinstance(md, dict):
                mode = md.get("mode") or md.get("transport_type")
                route_type = md.get("route_type") or md.get("road_type")
            else:
                extras = getattr(md, "extras", None)
                if isinstance(extras, dict):
                    mode = extras.get("mode")
                    route_type = extras.get("route_type")
                else:
                    mode = getattr(md, "mode", None) or getattr(arc, "mode", None)
                    route_type = getattr(md, "route_type", None) or getattr(arc, "route_type", None)

            if speed_def is None:
                speed_def = MODE_AVG_SPEED_KMH.get(str(mode).strip().lower(), MODE_AVG_SPEED_KMH.get("default"))

            if mode and str(mode).strip().lower() in ("truck", "camion", "truck_trailer"):
                mult = TRUCK_ROUTE_MULTIPLIER.get(str(route_type).strip().lower(), TRUCK_ROUTE_MULTIPLIER.get("default", 0.9))
                speed_def = float(speed_def) * float(mult)

            speeds.append(speed_def or MODE_AVG_SPEED_KMH.get("default"))
            modes.append(mode)
            route_types.append(route_type)

            # Coordenadas para cálculo vectorizado
            lat_u.append(origin.lat)
            lon_u.append(origin.lon)
            lat_v.append(dest.lat)
            lon_v.append(dest.lon)

            # Capacity
            cap_val, cap_unit = None, None
            if isinstance(md, dict):
                cap_val = md.get("capacity")
                cap_unit = md.get("capacity_unit")
            else:
                extras = getattr(md, "extras", None)
                if isinstance(extras, dict):
                    cap_val = extras.get("capacity")
                    cap_unit = extras.get("capacity_unit")
                else:
                    cap_val = getattr(md, "capacity", None)
                    cap_unit = getattr(md, "capacity_unit", None)

            if cap_val is None:
                data_cap.append(np.inf)
            else:
                try:
                    cap_f = float(cap_val)
                except Exception:
                    logger.warning("Arc %s capacity inválida '%s'; se marca como sin límite",
                                   getattr(arc, "id", "<no-id>"), cap_val)
                    data_cap.append(np.inf)
                    continue

                if cap_unit:
                    conv = UNIT_CONVERSIONS_TO_TON.get(str(cap_unit).lower())
                    if conv is not None:
                        cap_f *= float(conv)
                    else:
                        logger.warning("Arc %s capacity_unit desconocida '%s'; se asume toneladas",
                                       getattr(arc, "id", "<no-id>"), cap_unit)

                threshold = MODE_MAX_CAPACITY.get("default", 1e7)
                if mode:
                    threshold = MODE_MAX_CAPACITY.get(str(mode).strip().lower(), threshold)

                if cap_f < 0:
                    logger.warning("Arc %s tiene capacity negativa %s; se pone 0", getattr(arc, "id", "<no-id>"), cap_f)
                    data_cap.append(0.0)
                elif cap_f > threshold:
                    logger.warning("Arc %s capacity %s (ton) excede umbral para modo '%s' (%s ton); se clampa a %s",
                                   getattr(arc, "id", "<no-id>"), cap_f, mode or "unknown", threshold, threshold)
                    data_cap.append(float(threshold))
                else:
                    data_cap.append(float(cap_f))

        # Vectorizar distancias y tiempos
        lat_u, lon_u, lat_v, lon_v = map(np.array, (lat_u, lon_u, lat_v, lon_v))
        distances = vectorized_haversine(lat_u, lon_u, lat_v, lon_v)
        data_cost = np.array(data_cost, dtype=np.float32) * distances
        data_time = distances / np.array(speeds, dtype=np.float32)

        # Construcción dispersa
        A = csr_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)), shape=(n, n))
        C = csr_matrix((data_cost, (rows, cols)), shape=(n, n))
        T = csr_matrix((data_time, (rows, cols)), shape=(n, n))
        K = csr_matrix((np.array(data_cap, dtype=np.float32), (rows, cols)), shape=(n, n))

        # Vector de demanda
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
                "demand": "units",
            },
            "node_index": self._node_order.copy(),
            "mode_thresholds": MODE_MAX_CAPACITY.copy(),
            "mode_frequency": MODE_FREQUENCY_WEIGHT.copy(),
            "mode_avg_speed_kmh": MODE_AVG_SPEED_KMH.copy(),
            "truck_route_multiplier": TRUCK_ROUTE_MULTIPLIER.copy(),
        }

        return {
            "nodes": self._node_order.copy(),
            "A": A,
            "C": C,
            "T": T,
            "K": K,
            "D": vec_d,
            "meta": meta,
        }

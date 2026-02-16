# src/bloque1/topology.py
import logging
from typing import Dict, List, Any
import numpy as np
from scipy.sparse import csr_matrix

# Intentamos importar configuraciones, si no existen, el sistema usa defaults internos
try:
    from .config import (
        MODE_MAX_CAPACITY,
        MODE_AVG_SPEED_KMH,
        TRUCK_ROUTE_MULTIPLIER,
        UNIT_CONVERSIONS_TO_TON
    )
except ImportError:
    # SAFE DEFAULTS (Rigor de supervivencia)
    MODE_MAX_CAPACITY = {"default": 1e7, "truck": 45.0}
    MODE_AVG_SPEED_KMH = {"default": 60.0, "truck": 70.0}
    TRUCK_ROUTE_MULTIPLIER = {"default": 0.9, "highway": 1.0}
    UNIT_CONVERSIONS_TO_TON = {"kg": 0.001, "ton": 1.0, "lb": 0.00045}

logger = logging.getLogger(__name__)
EARTH_RADIUS_KM = 6371.0

def vectorized_haversine(lat1, lon1, lat2, lon2):
    """Calcula distancia entre arrays de coordenadas en km."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dlam/2)**2
    return EARTH_RADIUS_KM * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

class TopologyBuilder:
    """Fábrica de Matrices: Traduce el mundo físico a matemática pura."""
    
    def __init__(self, indexer):
        self.indexer = indexer
        self._node_order: List[str] = []
        self._built = False
        # Contenedores de matrices base
        self.A = None
        self.C = None
        self.T = None
        self.K = None
        self.D = None

    def build_topology(self) -> None:
        """Paso 1: Indexar nodos y validar estructura."""
        logger.info("Construyendo topología...")
        self._node_order = list(self.indexer.get_all_node_ids())
        if not self._node_order:
            raise RuntimeError("Error Crítico: El indexer no tiene nodos registrados.")
        self._built = True
        logger.info("Topología finalizada. %d nodos listos.", len(self._node_order))

    def export_matrices(self, sparse: bool = False) -> Dict[str, Any]:
        """Paso 2: Generar y exportar la pentada de matrices (A, C, T, K, D)."""
        if not self._built:
            raise RuntimeError("Debe llamar a build_topology() antes de exportar.")

        n = len(self._node_order)
        idx_map = {nid: i for i, nid in enumerate(self._node_order)}
        
        # Estructuras de datos para construcción
        rows, cols = [], []
        d_cost, d_cap = [], []
        lat_u, lon_u, lat_v, lon_v = [], [], [], []
        speeds = []

        # PROCESAMIENTO DE ARCOS
        for arc in self.indexer.iter_arcs():
            if not getattr(arc, "active", True):
                continue
            
            origin = self.indexer.get_node(arc.origin)
            dest = self.indexer.get_node(arc.destination)
            if not origin or not dest:
                continue

            i, j = idx_map[origin.id], idx_map[dest.id]
            rows.append(i)
            cols.append(j)

            # 1. Capacidad (Rigor: Usamos el campo que agregamos al ArcRecord)
            cap_val = getattr(arc, "capacity", 10000.0)
            d_cap.append(float(cap_val) if cap_val is not None else 10000.0)

            # -------------------------------------------------------
            # 2. Perfil de Velocidad y Modo (CORREGIDO MULTI-MODAL)
            # -------------------------------------------------------
            mode = "truck" # Default seguro
            
            # Intentamos extraer el modo real de la metadata
            if arc.metadata:
                if hasattr(arc.metadata, "extras") and isinstance(arc.metadata.extras, dict):
                     # Caso normal: Metadata es objeto y tiene dict extras
                     mode = arc.metadata.extras.get("mode", "truck")
                elif isinstance(arc.metadata, dict):
                     # Caso borde: Metadata es un dict directo
                     mode = arc.metadata.get("mode", "truck")

            # Normalizamos (ej: "Avion" -> "avion") para matchear config
            mode = str(mode).strip().lower()

            # Buscamos velocidad base en config (ej: air=800, truck=80)
            speed_default = MODE_AVG_SPEED_KMH.get("default", 50.0)
            speed_base = MODE_AVG_SPEED_KMH.get(mode, speed_default)

            # Si el arco tiene un perfil de velocidad específico (override), lo usamos
            if hasattr(arc, "speed_profile") and arc.speed_profile:
                if hasattr(arc.speed_profile, "default") and arc.speed_profile.default > 0:
                     speed_base = arc.speed_profile.default

            speeds.append(speed_base)
            # -------------------------------------------------------

            # 3. Coordenadas para Haversine
            lat_u.append(origin.lat)
            lon_u.append(origin.lon)
            lat_v.append(dest.lat)
            lon_v.append(dest.lon)
            
            # 4. Coeficiente de Costo Variable
            var_coef = 1.0
            if hasattr(arc, 'cost_profile') and arc.cost_profile:
                var_coef = getattr(arc.cost_profile, 'variable_coef', 1.0)
            d_cost.append(var_coef)

        # CÁLCULOS VECTORIZADOS (NumPy Power)
        dist = vectorized_haversine(np.array(lat_u), np.array(lon_u), np.array(lat_v), np.array(lon_v))
        final_costs = np.array(d_cost) * dist
        # Evitamos división por cero en tiempo
        final_times = dist / np.where(np.array(speeds) > 0, np.array(speeds), 1.0)

        # CONSTRUCCIÓN DE MATRICES
        A = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
        C = csr_matrix((final_costs, (rows, cols)), shape=(n, n))
        T = csr_matrix((final_times, (rows, cols)), shape=(n, n))
        K = csr_matrix((np.array(d_cap), (rows, cols)), shape=(n, n))

        if not sparse:
            A, C, T, K = A.toarray(), C.toarray(), T.toarray(), K.toarray()

        # VECTOR DE DEMANDA (D)
        vec_d = np.zeros(n, dtype=float)
        for i, nid in enumerate(self._node_order):
            node = self.indexer.get_node(nid)
            if node:
                vec_d[i] = float(getattr(node, "demand", 0.0)) - float(getattr(node, "supply", 0.0))

        # METADATOS PARA EL BLOQUE 2
        meta = {
            "base_k_sum": np.sum(K[np.isfinite(K)]),
            "base_a_sum": np.sum(A > 0),
            "units": {"distance": "km", "time": "hours"}
        }

        return {
            "nodes": self._node_order.copy(),
            "A": A, "C": C, "T": T, "K": K, "D": vec_d,
            "meta": meta
        }
#assembler.py
import logging
import math
from typing import Any, Mapping, Optional
from types import MappingProxyType

from .schema import Graph, Node, Edge
from .weight_builder import build_edge_weights as build_weights

LOGGER = logging.getLogger(__name__)

class GraphAssembler:
    """
    Ensamblador de Grafos: Transforma datos crudos en una red optimizable.
    Calcula distancias geodésicas (GPS) si no vienen pre-calculadas.
    """

    # Tarifas base ($/km)
    RATES = {
        "truck": 2.5,
        "air": 18.0
    }

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calcula distancia en km entre dos coordenadas (Fórmula Haversine)."""
        R = 6371.0  # Radio de la Tierra en km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
        return R * c

    @classmethod
    def assemble(
        cls,
        indexer,
        node_ids,
        fragility_map: Mapping[str, float],
        reliability_report: Optional[Mapping[str, Mapping[str, Any]]] = None
    ) -> Graph:
        """
        Construye el Grafo final calculando costos reales.
        - indexer: objeto que expone _arcs (mapping arc_id -> arc_data) y get_node(id)
        - node_ids: iterable de node ids
        - fragility_map: mapping node_id -> fragility probability
        - reliability_report: optional precomputed weights to inject via build_weights
        """
        b4_nodes = [Node(node_id=nid) for nid in node_ids]
        b4_edges = []

        for arc_id, arc_data in getattr(indexer, "_arcs", {}).items():
            # 1. Recuperar Nodos (Necesitamos sus coordenadas para medir distancia)
            origin_node = indexer.get_node(getattr(arc_data, "origin", None))
            dest_node = indexer.get_node(getattr(arc_data, "destination", None))

            if origin_node is None or dest_node is None:
                LOGGER.warning("Arco %s con nodos inexistentes (%s -> %s). Saltando.", arc_id,
                               getattr(arc_data, "origin", None), getattr(arc_data, "destination", None))
                continue

            # 2. Extracción del Modo (defensivo)
            mode = getattr(arc_data, "mode", None)
            metadata = getattr(arc_data, "metadata", None)
            if not mode and metadata:
                mode = getattr(metadata, "mode", None)
                if not mode and hasattr(metadata, "extras"):
                    extras = getattr(metadata, "extras", None)
                    if isinstance(extras, dict):
                        mode = extras.get("mode")

            if not mode:
                mode = "truck"

            # 3. Cálculo de Distancia (Self-Healing)
            distancia = float(getattr(arc_data, "distance", 0.0) or 0.0)
            # Si no hay coordenadas válidas, evitamos excepción y dejamos distancia 0
            try:
                if distancia <= 0.001:
                    lat1 = getattr(origin_node, "lat", None)
                    lon1 = getattr(origin_node, "lon", None)
                    lat2 = getattr(dest_node, "lat", None)
                    lon2 = getattr(dest_node, "lon", None)
                    if None not in (lat1, lon1, lat2, lon2):
                        distancia = cls._haversine(float(lat1), float(lon1), float(lat2), float(lon2))
                    else:
                        LOGGER.debug("Coordenadas faltantes para arco %s; distancia queda en 0.0", arc_id)
                        distancia = 0.0
            except Exception:
                LOGGER.exception("Error calculando distancia Haversine para arco %s", arc_id)
                distancia = 0.0

            # 4. Cálculo de Costo Monetario (defensivo)
            costo_final = 0.0
            costo_excel = 0.0
            cost_profile = getattr(arc_data, "cost_profile", None)
            if cost_profile:
                try:
                    if getattr(cost_profile, "cost_type", "") == "flat":
                        params = getattr(cost_profile, "params", {}) or {}
                        costo_excel = float(params.get("variable_coef", 0.0))
                except Exception:
                    LOGGER.debug("Cost profile mal formado en arco %s", arc_id)

            if costo_excel > 0:
                costo_final = costo_excel
            else:
                original_cost = 0.0
                if metadata and hasattr(metadata, "extras"):
                    extras = getattr(metadata, "extras", None) or {}
                    if isinstance(extras, dict):
                        original_cost = float(extras.get("original_cost", 0.0) or 0.0)
                if original_cost > 0.0:
                    costo_final = original_cost
                else:
                    tarifa = cls.RATES.get(str(mode).lower(), cls.RATES["truck"])
                    costo_final = float(distancia) * float(tarifa)

            # 5. Riesgo (defensivo)
            target_node = getattr(arc_data, "destination", None)
            target_node_risk = float(fragility_map.get(target_node, 0.0) or 0.0)
            risk_prob = min(max(target_node_risk, 0.0), 0.9999)

            # 6. Ensamblaje: asegurar campos mínimos esperados por el engine/profiler
            edge = Edge(
                edge_id=str(arc_id),
                source=str(getattr(arc_data, "origin", "")),
                target=str(getattr(arc_data, "destination", "")),
                cost=float(costo_final),
                distance=float(distancia),
                mode=str(mode),
                risk=float(risk_prob),
                # Campos adicionales que pueden ser rellenados por build_weights
                risk_weight=float(0.0),
                w_survival=float(0.0),
                w_expected_cost=float(0.0)
            )
            b4_edges.append(edge)

        # Inyectar pesos preprocesados si se proporcionó reliability_report
        if reliability_report is not None:
            try:
                build_weights(b4_edges, reliability_report)
            except Exception as exc:
                LOGGER.exception("build_weights failed while assembling graph: %s", exc)

        # Construir indexer inmutable (coherente con otros módulos)
        edge_index = {e.edge_id: i for i, e in enumerate(b4_edges)}
        return Graph(
            nodes=b4_nodes,
            edges=b4_edges,
            edge_indexer=MappingProxyType(edge_index)
        )

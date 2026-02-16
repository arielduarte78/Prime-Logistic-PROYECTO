import logging
import math
from .schema import Graph, Node, Edge

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
    def _haversine(lat1, lon1, lat2, lon2):
        """Calcula distancia en km entre dos coordenadas (Fórmula Haversine)."""
        R = 6371.0  # Radio de la Tierra en km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @classmethod
    def assemble(cls, indexer, node_ids, fragility_map):
        """
        Construye el Grafo final calculando costos reales.
        """
        b4_nodes = [Node(node_id=nid) for nid in node_ids]
        b4_edges = []

        for arc_id, arc_data in indexer._arcs.items():
            # 1. Recuperar Nodos (Necesitamos sus coordenadas para medir distancia)
            origin_node = indexer.get_node(arc_data.origin)
            dest_node = indexer.get_node(arc_data.destination)

            if not origin_node or not dest_node:
                LOGGER.warning(f"Arco {arc_id} con nodos inexistentes. Saltando.")
                continue

            # 2. Extracción del Modo
            mode = getattr(arc_data, 'mode', None)
            if not mode and arc_data.metadata:
                mode = getattr(arc_data.metadata, 'mode', None)
                if not mode and hasattr(arc_data.metadata, 'extras'):
                    extras = arc_data.metadata.extras
                    if isinstance(extras, dict):
                        mode = extras.get('mode')
            if not mode:
                mode = "truck"

            # 3. Cálculo de Distancia (Self-Healing)
            # Intentamos leer la distancia que traiga el arco. Si es 0, la calculamos.
            distancia = getattr(arc_data, 'distance', 0.0)
            
            if distancia <= 0.001: # Si es prácticamente 0
                distancia = cls._haversine(
                    origin_node.lat, origin_node.lon,
                    dest_node.lat, dest_node.lon
                )

            # 4. Cálculo de Costo Monetario
            costo_excel = 0.0
            if hasattr(arc_data, 'cost_profile') and arc_data.cost_profile:
                 if arc_data.cost_profile.cost_type == "flat":
                     costo_excel = arc_data.cost_profile.params.get("variable_coef", 0.0)
            
            if costo_excel <= 0 and hasattr(arc_data, 'metadata'):
                if hasattr(arc_data.metadata, 'extras') and isinstance(arc_data.metadata.extras, dict):
                     costo_excel = float(arc_data.metadata.extras.get("original_cost", 0.0))

            if costo_excel > 0:
                costo_final = costo_excel
            else:
                # Costo = Km * Tarifa del Modo
                tarifa = cls.RATES.get(str(mode).lower(), cls.RATES["truck"])
                costo_final = distancia * tarifa

            # 5. Riesgo
            target_node_risk = fragility_map.get(arc_data.destination, 0.0)
            risk_prob = min(target_node_risk, 0.9999)

            # 6. Ensamblaje
            b4_edges.append(Edge(
                edge_id=arc_id,
                source=arc_data.origin,
                target=arc_data.destination,
                cost=float(costo_final),
                distance=float(distancia),
                mode=str(mode),
                risk=float(risk_prob)
            ))

        return Graph(
            nodes=b4_nodes,
            edges=b4_edges,
            edge_indexer={e.edge_id: i for i, e in enumerate(b4_edges)}
        )
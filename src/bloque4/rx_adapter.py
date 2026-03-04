#src/bloque4/rx_adapter.py
import logging
import math
import time
from types import MappingProxyType
from typing import Dict, Tuple, Optional

import rustworkx as rx

from src.bloque4.schema import Graph, Node, Edge, OptimizerConfig
from src.bloque1.graph_builder import EdgePayload
from src.bloque3.bayesian_judge import BayesianJudge
from src.config.settings import load_cost_settings
from src.bloque3.threat_loader import load_h3_threat_matrix

THREAT_MATRIX = load_h3_threat_matrix()
COST_ENV = load_cost_settings()

# Parámetro del modelo matemático: longitud típica de ruta urbana AMBA (km)
# Usado para normalizar la exposición patrimonial por arista.
RUTA_TIPICA_KM = 10.0

logger = logging.getLogger("RX_Adapter")

def build_legacy_graph(
    rx_graph: rx.PyDiGraph,
    rx_to_osm: Dict[int, int],
    judge: BayesianJudge,
    source_rx_idx: int,
    target_rx_idx: int
) -> Tuple[Graph, OptimizerConfig, Dict[str, Tuple[float, float]]]:
    
    start_time = time.time()
    logger.info("Construyendo grafo legacy desde instanciacion rustworkx...")
    
    nodes = []
    node_coords: Dict[str, Tuple[float, float]] = {}
    
    for rx_idx in rx_graph.node_indices():
        node_id_str = str(rx_idx)
        node_payload = rx_graph[rx_idx]
        lat = getattr(node_payload, 'lat', 0.0)
        lon = getattr(node_payload, 'lon', 0.0)
        nodes.append(Node(node_id=node_id_str, lat=lat, lon=lon))
        if lat != 0.0 or lon != 0.0:
            node_coords[node_id_str] = (lat, lon)
        
    HIGHWAY_TOLL = {"motorway", "motorway_link", "trunk", "trunk_link"}
    
    edges = []
    for i, (u_rx, v_rx, payload) in enumerate(rx_graph.weighted_edge_list()):
        if not isinstance(payload, EdgePayload):
            continue

        beta_params = judge.get_params(u_rx, v_rx)
        p_survival = beta_params.alpha / (beta_params.alpha + beta_params.beta)
        p_failure = 1.0 - p_survival
        w_survival = -math.log(max(p_survival, 1e-9))

        dist_km = payload.length / 1000.0
        time_hr = dist_km / COST_ENV.velocidad_comercial_kmh
        financial_cost_ars = (dist_km * COST_ENV.c_km_ars) + (time_hr * COST_ENV.c_hora_ars)

        # Armed escort: cost proportional to the actual time spent in the red zone
        if payload.h3_index and payload.h3_index in THREAT_MATRIX:
            mu = THREAT_MATRIX[payload.h3_index]
            guardia_cost = time_hr * COST_ENV.custodia_hora_ars * mu
            financial_cost_ars += guardia_cost
            
        # AMBA exact tolls (March 2026 Report)
        if payload.highway in HIGHWAY_TOLL:
            name_upper = payload.name.upper() if payload.name else ""
            if "25 DE MAYO" in name_upper or "PERITO MORENO" in name_upper:
                financial_cost_ars += COST_ENV.ausa_25_mayo_ars
            elif "PASEO DEL BAJO" in name_upper or "BAJO" in name_upper:
                financial_cost_ars += COST_ENV.ausa_paseo_bajo_ars
            elif ("PANAMERICANA" in name_upper or "ACCESO NORTE" in name_upper
                  or "ACCESO OESTE" in name_upper):
                financial_cost_ars += COST_ENV.acceso_norte_oeste_ars
            elif ("BUENOS AIRES - LA PLATA" in name_upper
                  or "BUENOS AIRES-LA PLATA" in name_upper
                  or "RICCHERI" in name_upper):
                financial_cost_ars += COST_ENV.aubasa_sur_ars
            else:
                financial_cost_ars += COST_ENV.peaje_promedio_ars

        # Asset exposure proportional to the route fraction
        route_fraction = dist_km / RUTA_TIPICA_KM
        risk_cost_ars = p_failure * COST_ENV.franquicia_ars * route_fraction
        
        w_expected_cost = financial_cost_ars + risk_cost_ars

        edge = Edge(
            edge_id=f"{u_rx}_{v_rx}_{i}",
            source=str(u_rx),
            target=str(v_rx),
            cost=w_expected_cost,
            distance=payload.length,
            mode="truck",
            time=time_hr * 3600, # time in seconds to match previous behavior implicitly or keep it schema compatible (previous was sec)
            risk=p_failure,
            risk_weight=w_survival,
            w_survival=w_survival,
            w_expected_cost=w_expected_cost
        )
        edges.append(edge)
        
    edge_indexer = MappingProxyType({edge.edge_id: i for i, edge in enumerate(edges)})
    
    graph = Graph(
        nodes=nodes,
        edges=edges,
        edge_indexer=edge_indexer
    )
    
    config = OptimizerConfig(
        source_node_id=str(source_rx_idx),
        target_node_id=str(target_rx_idx),
        require_full_connectivity=False
    )
    
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info("Grafo legacy construido en %.2f ms | %d nodos con coordenadas", elapsed_ms, len(node_coords))
    
    financial_summary = {
        "total_edges": len(edges),
        "avg_cost_per_edge_ars": sum(e.w_expected_cost for e in edges) / max(len(edges), 1),
        "dolar_mep": COST_ENV.dolar_mep_ars,
        "c_km_ars": COST_ENV.c_km_ars
    }

    return graph, config, financial_summary

def get_rx_idx_for_osm(osm_to_rx: Dict[int, int], osm_id: int) -> Optional[int]:
    return osm_to_rx.get(osm_id)

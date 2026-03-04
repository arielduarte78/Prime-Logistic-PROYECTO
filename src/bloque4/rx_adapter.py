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
        
    edges = []
    for i, (u_rx, v_rx, payload) in enumerate(rx_graph.weighted_edge_list()):
        if not isinstance(payload, EdgePayload):
            continue
            
        beta_params = judge.get_params(u_rx, v_rx)
        survival_probability = beta_params.alpha / (beta_params.alpha + beta_params.beta)
        w_survival = -math.log(max(survival_probability, 1e-9))
        p_failure = 1.0 - survival_probability
        w_expected_cost = payload.length + (p_failure * payload.length)
        
        # Estimación de tiempo de tránsito (length en metros, velocidad ~50 km/h = 13.89 m/s)
        estimated_time = payload.length / 13.89 if payload.length > 0 else 0.0
        
        edge = Edge(
            edge_id=f"{u_rx}_{v_rx}_{i}",
            source=str(u_rx),
            target=str(v_rx),
            cost=w_expected_cost,
            distance=payload.length,
            mode="truck",
            time=estimated_time,
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
    
    return graph, config, node_coords

def get_rx_idx_for_osm(osm_to_rx: Dict[int, int], osm_id: int) -> Optional[int]:
    return osm_to_rx.get(osm_id)

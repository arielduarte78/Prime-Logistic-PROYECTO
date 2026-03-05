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

from src.bloque4.lazy_graph import LazyEdgeView

THREAT_MATRIX = load_h3_threat_matrix()

# Parámetro del modelo matemático: longitud típica de ruta urbana AMBA (km)
# Usado para normalizar la exposición patrimonial por arista.
RUTA_TIPICA_KM = 10.0

logger = logging.getLogger("RX_Adapter")

def build_legacy_graph(
    rx_graph: rx.PyDiGraph,
    rx_to_osm: Dict[int, int],
    judge: BayesianJudge,
    source_rx_idx: int,
    target_rx_idx: int,
    cost_env: Any,
    allowed_nodes: set[int]
) -> Tuple[Any, OptimizerConfig, Dict[str, float]]:
    
    start_time = time.time()
    logger.info("Construyendo proxy LazyEdgeView desde instanciacion rustworkx...")
    
    graph = LazyEdgeView(
        rx_graph=rx_graph,
        allowed_nodes=allowed_nodes,
        cost_env=cost_env,
        threat_matrix=THREAT_MATRIX,
        ruta_tipica_km=RUTA_TIPICA_KM,
        judge=judge
    )
    
    config = OptimizerConfig(
        source_node_id=str(source_rx_idx),
        target_node_id=str(target_rx_idx),
        require_full_connectivity=False
    )
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    import itertools
    sample_edges = list(itertools.islice(graph.edges, 500))
    avg_cost = sum(e.w_expected_cost for e in sample_edges) / max(len(sample_edges), 1)
    
    logger.info("LazyEdgeView construido en %.2f ms | Nodos permitidos: %d", elapsed_ms, len(allowed_nodes))
    
    financial_summary = {
        "avg_cost_per_edge_ars": avg_cost,
        "dolar_mep": cost_env.dolar_mep_ars,
        "c_km_ars": cost_env.c_km_ars
    }

    return graph, config, financial_summary

def get_rx_idx_for_osm(osm_to_rx: Dict[int, int], osm_id: int) -> Optional[int]:
    return osm_to_rx.get(osm_id)

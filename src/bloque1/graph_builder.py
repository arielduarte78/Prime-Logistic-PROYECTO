import time
import logging
from dataclasses import dataclass
from typing import Dict, Tuple

import pandas as pd
import rustworkx as rx

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("Graph_Builder")

# ====================================================================
# Data Contracts (Consumed by Blocks 2, 3 and 4)
# ====================================================================

@dataclass(frozen=True)
class EdgePayload:
    """
    Immutable payload stored in every directed edge of the rustworkx graph.
    """
    u_osm: int
    v_osm: int
    alpha_prior: float
    beta_prior: float
    length: float = 0.0
    highway: str = "unclassified"

# ====================================================================
# Graph Instantiation Engine
# ====================================================================

def build_directed_graph(df_edges: pd.DataFrame) -> Tuple[rx.PyDiGraph, Dict[int, int], Dict[int, int]]:
    """
    Constructs a high-performance rustworkx PyDiGraph directly from a duckdb DataFrame.
    Returns:
    - graph: The instantiated rustworkx PyDiGraph
    - osm_to_rx: Mapping from OSM node IDs to internal rustworkx indices
    - rx_to_osm: Mapping from internal rustworkx indices to OSM node IDs
    """
    logger.info("Initializing rustworkx high-speed graph construction...")
    
    # Pre-allocate mappings
    osm_to_rx: Dict[int, int] = {}
    rx_to_osm: Dict[int, int] = {}
    
    # Initialize Directed Graph (Multigraph capable by default, but we treat it as standard DiGraph)
    graph = rx.PyDiGraph()
    
    # ----------------------------------------------------------------
    # Step 1: Register Unique Nodes (Vectorized Extraction)
    # ----------------------------------------------------------------
    t0_nodes = time.time()
    
    if not df_edges.empty:
        # Extract all unique nodes involved in edges in O(1) vectorized operation
        unique_nodes = pd.unique(df_edges[['u', 'v']].values.ravel())
        
        # Populate rustworkx nodes and dictionary mappings
        for osm_id in unique_nodes:
            osm_int = int(osm_id)
            rx_idx = graph.add_node(osm_int)
            osm_to_rx[osm_int] = rx_idx
            rx_to_osm[rx_idx] = osm_int
            
    t1_nodes = time.time()
    logger.info(f"Registered {len(osm_to_rx)} unique nodes in {(t1_nodes - t0_nodes) * 1000:.2f} ms")
    
    # ----------------------------------------------------------------
    # Step 2: Build Edges Iterator
    # ----------------------------------------------------------------
    t0_edges = time.time()
    
    if not df_edges.empty:
        # Check if length column exists, otherwise fallback to 0.0
        has_length = "length" in df_edges.columns
        
        edges_added = 0
        
        # Use itertuples for max performance over DataFrame row iteration
        for row in df_edges.itertuples(index=False):
            # Extract standard values
            u_osm = int(row.u) # type: ignore
            v_osm = int(row.v) # type: ignore
            alpha = float(row.alpha_prior) # type: ignore
            beta = float(row.beta_prior) # type: ignore
            
            # Extract optional values
            length_val = float(row.length) if has_length else 0.0 # type: ignore
            highway_val = str(row.highway) if "highway" in df_edges.columns else "unclassified" # type: ignore
            
            # Translate OSM identifiers to Rustworkx array indices
            u_rx = osm_to_rx[u_osm]
            v_rx = osm_to_rx[v_osm]
            
            # Instantiate frozen dataclass payload
            payload = EdgePayload(
                u_osm=u_osm,
                v_osm=v_osm,
                alpha_prior=alpha,
                beta_prior=beta,
                length=length_val,
                highway=highway_val
            )
            
            # Inject into the C/Rust engine
            graph.add_edge(u_rx, v_rx, payload)
            edges_added += 1
            
    t1_edges = time.time()
    logger.info(f"Instantiated {edges_added if not df_edges.empty else 0} directed edges with payloads in {(t1_edges - t0_edges) * 1000:.2f} ms")
    
    return graph, osm_to_rx, rx_to_osm

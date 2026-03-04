#graph_adapter.py
import time
import logging
import numpy as np
import rustworkx as rx
from src.bloque1.graph_builder import EdgePayload

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("Graph_Adapter")

def get_matrices(graph: rx.PyDiGraph) -> tuple:
    """
    Extracts high-performance vectorized NumPy matrices representing the
    edge parameters for Monte Carlo simulation in Block 2.
    """
    logger.info("Initializing Graph to Matrix extraction for Block 2...")
    start_time = time.time()
    
    # Handle the empty graph case safely to prevent ValueError during extraction
    if graph.num_edges() == 0:
        logger.warning("Graph is completely empty. Returning empty numpy matrix boundaries.")
        empty_idx = np.empty((0, 2), dtype=np.int32)
        empty_c = np.empty(0, dtype=np.float32)
        empty_a = np.empty(0, dtype=np.float32)
        empty_b = np.empty(0, dtype=np.float32)
        return empty_idx, empty_c, empty_a, empty_b
    
    # Fast iteration over rustworkx elements using explicitly weighted edges
    # Result -> list of tuples (u_rx, v_rx, EdgePayload)
    weighted_edges = graph.weighted_edge_list()
    
    # Intermediate Python list compilation to avoid Numpy incremental array appending (Slow O(N^2))
    edges_list = [(u, v, p.length, p.alpha_prior, p.beta_prior) for u, v, p in weighted_edges]
    
    # Translation to CPU cache-coherent continuous arrays
    edges_idx = np.array([(e[0], e[1]) for e in edges_list], dtype=np.int32)
    
    # C array represents standard network costs (Lengths)
    C = np.array([e[2] for e in edges_list], dtype=np.float32)
    
    # A array represents the Alpha parameter of the Beta distribution Prior
    A = np.array([e[3] for e in edges_list], dtype=np.float32)
    
    # B array represents the Beta parameter of the Beta distribution Prior
    B = np.array([e[4] for e in edges_list], dtype=np.float32)
    
    elapsed_time = time.time() - start_time
    
    # Diagnostic Logs
    logger.info(f"Matrix Extraction Complete in {elapsed_time * 1000:.2f} ms")
    logger.info(f"Dimension edges_idx: (Rows: {edges_idx.shape[0]}, Cols: {edges_idx.shape[1]}) | Dtype: {edges_idx.dtype}")
    logger.info(f"Dimension array C: (Len: {C.shape[0]}, ) | Dtype: {C.dtype}")
    logger.info(f"Dimension array A: (Len: {A.shape[0]}, ) | Dtype: {A.dtype}")
    logger.info(f"Dimension array B: (Len: {B.shape[0]}, ) | Dtype: {B.dtype}")
    
    return edges_idx, C, A, B

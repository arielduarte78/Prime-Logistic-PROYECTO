#graph_adapter.py
import time
import logging
import numpy as np
import rustworkx as rx
from typing import Dict, Any
from src.bloque1.graph_builder import EdgePayload
import scipy.sparse as sp

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

def build_network_snapshot_from_rx(graph: rx.PyDiGraph):
    """
    Translates a rustworkx graph to the NetworkSnapshot format using scipy sparse matrices.
    Returns a NetworkSnapshot object that can be passed directly to MonteCarloGenerator.
    """
    logger.info("Translating rustworkx graph to NetworkSnapshot format...")
    
    # Import locally to avoid circular dependencies
    from src.bloque2.generator import NetworkSnapshot
    
    num_nodes = graph.num_nodes()
    
    # Extract edges
    weighted_edges = graph.weighted_edge_list()
    
    # We will build sparse matrices via coordinate format (COO)
    rows = []
    cols = []
    
    data_A = []  # Adjacency: 1 for connection
    data_C = []  # Cost (distance)
    data_T = []  # Time
    data_K = []  # Capacity
    data_D = []  # Density / friction
    
    for u, v, payload in weighted_edges:
        rows.append(u)
        cols.append(v)
        data_A.append(1.0)
        
        # Determine capacity and fallback to safe defaults if not present
        capacity = payload.lanes * 1500 if getattr(payload, 'lanes', None) else 1500.0
        
        # Basic parsing
        c_val = getattr(payload, 'length', 1.0)
        t_val = getattr(payload, 'travel_time', c_val / 40.0) # Assume 40 km/h baseline if missing
        
        data_C.append(c_val)
        data_T.append(t_val)
        data_K.append(capacity)
        data_D.append(1.0)  # Baseline density is 1.0
        
    A_sparse = sp.coo_matrix((data_A, (rows, cols)), shape=(num_nodes, num_nodes)).tocsr()
    C_sparse = sp.coo_matrix((data_C, (rows, cols)), shape=(num_nodes, num_nodes)).tocsr()
    T_sparse = sp.coo_matrix((data_T, (rows, cols)), shape=(num_nodes, num_nodes)).tocsr()
    K_sparse = sp.coo_matrix((data_K, (rows, cols)), shape=(num_nodes, num_nodes)).tocsr()
    D_sparse = sp.coo_matrix((data_D, (rows, cols)), shape=(num_nodes, num_nodes)).tocsr()
    
    # =========================================================================
    # CONGELAMIENTO ESTRUCTURAL (SciPy CSR Hardening)
    # Protege contra mutaciones topológicas e incrementa velocidad del .data
    # =========================================================================
    for mat in (A_sparse, C_sparse, T_sparse, K_sparse, D_sparse):
        mat.eliminate_zeros()
        mat.sort_indices()
    
    # Build string nodes representation for compat 
    str_nodes = [str(n) for n in range(num_nodes)]
    
    # Calculate initial meta
    meta = {
        'base_k_sum': K_sparse.sum(),
        'base_a_sum': A_sparse.nnz
    }
    
    return NetworkSnapshot(
        A=A_sparse,
        C=C_sparse,
        T=T_sparse,
        K=K_sparse,
        D=D_sparse,
        nodes=str_nodes,
        meta=meta
    )

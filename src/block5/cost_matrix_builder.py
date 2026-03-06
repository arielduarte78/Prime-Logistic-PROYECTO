# src/block5/cost_matrix_builder.py
import rustworkx as rx
from typing import List, Dict, Callable, Any
from src.block5.lambda_scalarizer import get_weight_function
from src.bloque1.graph_builder import NodePayload

UNREACHABLE_PENALTY = 999999999

def build_dense_cost_matrix(
    graph: rx.PyDiGraph,
    nodes_of_interest: List[int],
    archetype: str,
    cost_env: Any,
    threat_matrix: dict,
    judge: Any,
    osm_to_rx: dict
) -> List[List[int]]:
    """
    Given a list of node indices in the graph (combination of vehicles and destinations),
    computes an NxN dense cost matrix using rustworkx.dijkstra_shortest_path_lengths.

    Steps:
      - Obtains the weight_fn for the requested archetype.
      - Calls dijkstra ONCE per origin point.
      - Maps the sparse result into a complete strict Dense Matrix.
      - Multiplies costs by 100 and casts them to integers for OR-Tools compatibility.
      - Pads disconnected nodes with UNREACHABLE_PENALTY.

    Args:
        graph: The full PyDiGraph.
        nodes_of_interest: List of rustworkx node IDs (vehicles followed by destinations).
        archetype: The targeted archetype (e.g., 'equilibrista').

    Returns:
        A dense 2D list matrix `matrix[i][j]` representing scaled cost.
    """
    matrix: List[List[int]] = []
    
    weight_fn = get_weight_function(archetype, cost_env, threat_matrix, judge, osm_to_rx)
    
    n_size = len(nodes_of_interest)
    
    for i in range(n_size):
        origin_node = nodes_of_interest[i]
        
        # Call Rustworkx Dijkstra ONLY ONCE per origin
        # Returns a dict: {target_node_idx: cost_float, ...}
        # It calculates shortest path from origin_node to all reachable nodes.
        shortest_paths: Dict[int, float] = rx.dijkstra_shortest_path_lengths(
            graph, origin_node, edge_cost_fn=weight_fn
        )
        
        row: List[int] = []
        for j in range(n_size):
            dest_node = nodes_of_interest[j]
            
            if origin_node == dest_node:
                row.append(0)
            elif dest_node in shortest_paths:
                # Scale by 100 and convert to integer for OR-tools
                cost_int = int(shortest_paths[dest_node] * 100)
                row.append(cost_int)
            else:
                row.append(UNREACHABLE_PENALTY)
                
        matrix.append(row)
        
    return matrix

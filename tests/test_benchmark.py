import time
from src.bloque1.h3_router import build_h3_corridor
from src.bloque1.duckdb_ingestor import extract_subgraph_edges
from src.bloque1.graph_builder import build_directed_graph

def run_test():
    print("Starting Phase 2 & 3 Integration Test: Out-of-Core Extraction + Rustworkx Graph...")
    
    # Origin: Retiro (CABA) | Destination: Lanús Center
    origin = (-34.5900, -58.3700)
    destination = (-34.7000, -58.3900)
    
    # Geometric Router Test
    t0 = time.time()
    corridor_h3 = build_h3_corridor(origin_lat=origin[0], origin_lon=origin[1], dest_lat=destination[0], dest_lon=destination[1])
    t1 = time.time()
    
    print(f"Router completed in {(t1-t0)*1000:.2f} ms.")
    print(f"Hexagons in corridor (k=2): {len(corridor_h3)}")
    
    # SQL Extraction Test (DuckDB)
    t2 = time.time()
    df_subgraph = extract_subgraph_edges(corridor_h3)
    t3 = time.time()
    
    print(f"DuckDB SQL completed in {(t3-t2)*1000:.2f} ms.")
    print(f"Edges extracted to RAM: {len(df_subgraph)}")
    print(f"DataFrame weight in memory: {df_subgraph.memory_usage(deep=True).sum() / (1024*1024):.2f} MB")
    print("-" * 50)
    
    # Phase 3: High-Speed Graph Instantiation (Rustworkx)
    if not df_subgraph.empty:
        t4 = time.time()
        graph, osm_to_rx, rx_to_osm = build_directed_graph(df_subgraph)
        t5 = time.time()
        
        print(f"Graph Construction completed in {(t5-t4)*1000:.2f} ms.")
        print(f"Nodes in Graph: {graph.num_nodes()}")
        print(f"Edges in Graph: {graph.num_edges()}")
        
        print("\nSample of the extracted subgraph Edge (Payload validation):")
        # Grab any edge to check payload
        edge_list = graph.edge_list()
        if edge_list:
            u, v = edge_list[0]
            payload = graph.get_edge_data(u, v)
            print(f"First Edge - Payload: {payload}")
    else:
        print("Subgraph is empty, skipping Phase 3 benchmark.")

if __name__ == "__main__":
    run_test()

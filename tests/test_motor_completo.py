import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.bloque1.h3_router import build_h3_corridor
import time
from src.bloque1.h3_router import build_h3_corridor
from src.bloque1.duckdb_ingestor import extract_subgraph_edges
from src.bloque1.graph_builder import build_directed_graph
from src.bloque2.graph_adapter import get_matrices
from src.bloque3.bayesian_judge import BayesianJudge
from src.bloque4.weight_builder import build_pareto_edges

def run_test():
    print("==================================================")
    print(" IGNICIÓN DEL MOTOR PRIME V1.4 (FASES 1 A 4) ")
    print("==================================================")
    
    # Origen: Retiro (CABA) | Destino: Centro de Lanús
    origen = (-34.5900, -58.3700)
    destino = (-34.7000, -58.3900)
    
    print("\n[1/4] Extracción Out-of-Core...")
    t0 = time.time()
    corredor_h3 = build_h3_corridor(origin_lat=origen[0], origin_lon=origen[1], dest_lat=destino[0], dest_lon=destino[1])
    df_subgrafo = extract_subgraph_edges(corredor_h3)
    t1 = time.time()
    print(f"-> Parquet a RAM: {(t1-t0)*1000:.2f} ms ({len(df_subgrafo)} aristas)")
    
    print("\n[2/4] Instanciación Rustworkx...")
    t2 = time.time()
    grafo_rx, _, _ = build_directed_graph(df_subgrafo)
    t3 = time.time()
    print(f"-> Grafo C/Rust compilado en: {(t3-t2)*1000:.2f} ms")
    
    print("\n[3/4] Puente Matricial NumPy (Bloque 2)...")
    t4 = time.time()
    edges_idx, C, A, B = get_matrices(grafo_rx)
    t5 = time.time()
    print(f"-> Tensores C-Contiguous creados en: {(t5-t4)*1000:.2f} ms")
    
    print("\n[4/4] Inferencia Bayesiana y Pareto (Bloques 3 y 4)...")
    t6 = time.time()
    judge = BayesianJudge(grafo_rx)
    pareto_edges = build_pareto_edges(grafo_rx, judge)
    t7 = time.time()
    print(f"-> Juez y {len(pareto_edges)} Aristas Pareto listas en: {(t7-t6)*1000:.2f} ms")
    
    print("\n==================================================")
    print(f" TIEMPO TOTAL DE PROCESAMIENTO: {(t7-t0)*1000:.2f} ms")
    print("==================================================")
    
    if pareto_edges:
        print(f"\nAuditoría Pareto (Arista 0): {pareto_edges[0]}")

if __name__ == "__main__":
    run_test()
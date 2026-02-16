#debug_ingesta.py 
import sys
import os
import pandas as pd
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.bloque1.network import NetworkIndexer, Ingestor
from src.bloque1.loader import ExcelLoader
from src.bloque1.topology import TopologyBuilder

def auditar_final():
    print("\n🚀 INICIANDO VERIFICACIÓN MATEMÁTICA...")
    filename = Path(__file__).parent / "final_test.xlsx"

    # Datos reales: BsAs -> Córdoba (~700km)
    nodes = [
        {"id": "NODE_0001", "lat": -34.60, "lon": -58.38, "station_type": "warehouse"},
        {"id": "NODE_0002", "lat": -31.42, "lon": -64.18, "station_type": "warehouse"},
        {"id": "NODE_0003", "lat": -34.55, "lon": -58.41, "station_type": "airport"},
        {"id": "NODE_0004", "lat": -31.31, "lon": -64.21, "station_type": "airport"},
    ]
    
    arcs = [
        {"id": "ARC_0001", "origin": "NODE_0001", "destination": "NODE_0002", "mode": "truck", "capacity": 30},
        {"id": "ARC_0002", "origin": "NODE_0003", "destination": "NODE_0004", "mode": "air", "capacity": 10}
    ]

    try:
        with pd.ExcelWriter(filename) as writer:
            pd.DataFrame(nodes).to_excel(writer, sheet_name="NODES", index=False)
            pd.DataFrame(arcs).to_excel(writer, sheet_name="ARCS", index=False)
        
        indexer = NetworkIndexer()
        ingestor = Ingestor(indexer)
        loader = ExcelLoader(str(filename))
        loader.run(ingestor)

        # GENERAR MATRICES
        topo = TopologyBuilder(indexer)
        topo.build_topology()
        matrices = topo.export_matrices()
        
        nodes_list = matrices["nodes"]
        T = matrices["T"] # Matriz de Tiempos

        # Extraer tiempos usando los índices reales de los nodos
        idx_bsas = nodes_list.index("NODE_0001")
        idx_cba  = nodes_list.index("NODE_0002")
        idx_aep  = nodes_list.index("NODE_0003")
        idx_pajas = nodes_list.index("NODE_0004")

        t_camion = T[idx_bsas, idx_cba]
        t_avion  = T[idx_aep, idx_pajas]

        print("\n" + "—"*40)
        print("📊 VERIFICACIÓN DE TIEMPOS (Cálculo Haversine)")
        print("—"*40)
        print(f"🚛 CAMIÓN (ARC_0001): {t_camion:.2f} horas")
        print(f"✈️  AVIÓN  (ARC_0002): {t_avion:.2f} horas")
        print("—"*40)

        if t_avion > 0 and t_avion < t_camion:
            relacion = t_camion / t_avion
            print(f"✅ ¡ÉXITO! El avión es {relacion:.1f} veces más rápido que el camión.")
            print("El Bloque 1 está oficialmente vivo y es multi-modal.")
        else:
            print("❌ ALGO SALIÓ MAL: Los tiempos no son coherentes.")

    finally:
        if filename.exists(): 
            os.remove(filename)

if __name__ == "__main__":
    auditar_final()
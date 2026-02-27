#Test de integración para el proceso completo: desde Excel hasta matrices de topología. BLOQUE 1
import sys
import os
import logging
import pandas as pd
from pathlib import Path

# Truco para importar src desde una subcarpeta
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.bloque1.network import NetworkIndexer, Ingestor
from src.bloque1.loader import ExcelLoader
from src.bloque1.topology import TopologyBuilder

# Configurar logs
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("TEST")

def ejecutar_prueba():
    filename = Path(__file__).parent / "test_data_temp.xlsx"
    
    logger.info(f"🛠️  Generando Excel de prueba en: {filename}")
    
    # 1. NODOS
    nodes = [
        {"id": "NODE_0001", "lat": -34.60, "lon": -58.38, "station_type": "warehouse"}, # BsAs
        {"id": "NODE_0002", "lat": -31.42, "lon": -64.18, "station_type": "warehouse"}, # Córdoba
        {"id": "NODE_0003", "lat": -34.55, "lon": -58.41, "station_type": "airport"},   # Aeroparque
        {"id": "NODE_0004", "lat": -31.31, "lon": -64.21, "station_type": "airport"},   # Córdoba Aero
    ]
    
    # 2. ARCOS (CORREGIDO: IDs estrictos ARC_xxxx)
    # IMPORTANTE: En el Excel, la columna 'metadata' es texto JSON.
    arcs = [
        # CAMIÓN (BsAs -> Cba)
        {
            "id": "ARC_0001", 
            "origin": "NODE_0001", "destination": "NODE_0002", 
            "mode": "truck", "capacity": 30, 
            "speed_avg": 60, # Forzamos velocidad camión
            "metadata": "{}"
        },
        # AVIÓN (Aeroparque -> Cba Aero)
        {
            "id": "ARC_0002", 
            "origin": "NODE_0003", "destination": "NODE_0004", 
            "mode": "air", "capacity": 10,
            "metadata": '{"mode": "air"}' # JSON explícito para el modo
        }
    ]

    try:
        with pd.ExcelWriter(filename) as writer:
            pd.DataFrame(nodes).to_excel(writer, sheet_name="NODES", index=False)
            pd.DataFrame(arcs).to_excel(writer, sheet_name="ARCS", index=False)
        
        indexer = NetworkIndexer()
        ingestor = Ingestor(indexer)
        
        logger.info("⚡ Ejecutando Loader...")
        loader = ExcelLoader(str(filename))
        nodes_res, fleet_res = loader.run()

        # REPORTE DE ERRORES (Para ver por qué fallan)
        report = ingestor.get_validation_report()
        if report["error_count"] > 0:
            logger.warning("⚠️  ERRORES ENCONTRADOS DURANTE LA CARGA:")
            for err in report["errors"]:
                print(f"   [x] {err['code']}: {err['message']} (Contexto: {err.get('context')})")

        logger.info("🧪 Calculando Topología...")
        topo = TopologyBuilder(indexer)
        topo.build_topology()
        matrices = topo.export_matrices()
        
        # --- VERIFICACIÓN DE RESULTADOS ---
        # Si no se cargaron arcos, las matrices estarán vacías
        if report["arc_count"] == 0:
            logger.error("⛔ NO SE CARGARON ARCOS. PRUEBA ABORTADA.")
            return

        T = matrices["T"]
        nodes_orden = matrices["nodes"]
        
        # Buscamos índices
        idx_bsas = nodes_orden.index("NODE_0001")
        idx_cba  = nodes_orden.index("NODE_0002")
        idx_aep  = nodes_orden.index("NODE_0003")
        idx_cba_aero = nodes_orden.index("NODE_0004")

        t_camion = T[idx_bsas, idx_cba]
        t_avion  = T[idx_aep, idx_cba_aero]

        print("\n" + "="*40)
        print("       RESULTADOS DE LA PRUEBA")
        print("="*40)
        print(f"🚛 Tiempo Camión (~700km): {t_camion:.2f} horas")
        print(f"✈️  Tiempo Avión  (~700km): {t_avion:.2f} horas")
        
        if t_avion > 0 and t_avion < (t_camion / 5):
            print("\n✅ ÉXITO TOTAL: El sistema distingue modos de transporte.")
        else:
            print("\n❌ FALLO: Revisar cálculos.")

    except Exception as e:
        logger.error(f"La prueba falló con error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if filename.exists():
            os.remove(filename)

if __name__ == "__main__":
    ejecutar_prueba()
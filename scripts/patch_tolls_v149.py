#scripts/patch_tolls_v149.py
import numpy as np
import pandas as pd
import shutil
import sys
from pathlib import Path

def main():
    print(f"[*] Iniciando parcheo de peajes V1.4.9...")
    
    # Configurar rutas absolutas al proyecto
    ROOT_PATH = Path(__file__).resolve().parent.parent
    DATA_DIR = ROOT_PATH / "data" / "parquet_db"
    EDGES_PATH = DATA_DIR / "edges.parquet"
    NODES_PATH = DATA_DIR / "nodes.parquet"
    BACKUP_PATH = DATA_DIR / "edges_backup.parquet"
    
    # 1. Copia de seguridad estricta
    try:
        if not EDGES_PATH.exists():
            print(f"[ERROR] Archivo no encontrado: {EDGES_PATH}")
            sys.exit(1)
            
        print(f"[*] Creando backup en {BACKUP_PATH}...")
        shutil.copy2(EDGES_PATH, BACKUP_PATH)
        print("[*] Backup creado exitosamente.")
    except Exception as e:
        print(f"[ERROR FATAL] Falló la creación del backup: {e}")
        sys.exit(1)
        
    try:
        # 2. Cargar parquets
        print("[*] Cargando edges y nodes...")
        edges_df = pd.read_parquet(EDGES_PATH)
        nodes_df = pd.read_parquet(NODES_PATH)
        
        node_id_col = 'node_id' if 'node_id' in nodes_df.columns else ('osmid' if 'osmid' in nodes_df.columns else nodes_df.columns[0])
        lat_col = 'lat' if 'lat' in nodes_df.columns else 'y'
        lon_col = 'lon' if 'lon' in nodes_df.columns else 'x'
             
        # Merge to get u_lat, u_lon
        print("[*] Cruzando datos espaciales...")
        merged_df = edges_df.merge(
            nodes_df[[node_id_col, lat_col, lon_col]],
            left_on='u', right_on=node_id_col, how='left'
        )
        
        # 3. Aplicar heurísticas espaciales vectorizadas
        print("[*] Evaluando heurísticas espaciales...")
        
        # Ensure name column exists
        if 'name' not in edges_df.columns:
            edges_df['name'] = ""
        else:
            # fillna to avoid issues
            edges_df['name'] = edges_df['name'].fillna("")
            
        # condition for highway
        valid_highways = ['motorway', 'motorway_link', 'trunk', 'trunk_link']
        hw_mask = edges_df['highway'].isin(valid_highways)
        
        lat = merged_df[lat_col]
        lon = merged_df[lon_col]
        name = edges_df['name'].copy()
        
        # PANAMERICANA 
        m_pan = hw_mask & (lat > -34.56) & (lon < -58.40) & (lon > -59.00)
        
        # ACCESO OESTE 
        m_oes = hw_mask & (~m_pan) & (lat > -34.65) & (lat < -34.45) & (lon < -58.53)
        
        # 25 DE MAYO / PERITO MORENO 
        m_25m = hw_mask & (~m_pan) & (~m_oes) & (lat > -34.65) & (lat < -34.60) & (lon > -58.48) & (lon < -58.36)
        
        # PASEO DEL BAJO 
        m_bajo = hw_mask & (~m_pan) & (~m_oes) & (~m_25m) & (lat > -34.63) & (lat < -34.58) & (lon > -58.375)
        
        # BUENOS AIRES - LA PLATA
        m_sur = hw_mask & (~m_pan) & (~m_oes) & (~m_25m) & (~m_bajo) & (lat < -34.70) & (lon > -58.37) & (lon < -57.90)
        
        name[m_pan] = "PANAMERICANA"
        name[m_oes] = "ACCESO OESTE"
        name[m_25m] = "25 DE MAYO"
        name[m_bajo] = "PASEO DEL BAJO"
        name[m_sur] = "BUENOS AIRES - LA PLATA"
        
        edges_df['name'] = name
        
        counts = {
            "PANAMERICANA": int(m_pan.sum()),
            "ACCESO OESTE": int(m_oes.sum()),
            "25 DE MAYO": int(m_25m.sum()),
            "PASEO DEL BAJO": int(m_bajo.sum()),
            "BUENOS AIRES - LA PLATA": int(m_sur.sum())
        }
        
        # 4. Guardar resultado
        print("[*] Guardando edges.parquet actualizados...")
        edges_df.to_parquet(EDGES_PATH, index=False)
        
        print("\n--- REPORTE DE AUDITORIA V1.4.9 ---")
        for k, v in counts.items():
            print(f"- {k}: {v} aristas modificadas.")
        print("-----------------------------------")
        print("[*] Proceso finalizado exitosamente.")
        
    except Exception as e:
        print(f"[ERROR] Falló el procesamiento: {e}")
        print("[*] Restaurando backup...")
        if BACKUP_PATH.exists():
            shutil.copy2(BACKUP_PATH, EDGES_PATH)
        sys.exit(1)

if __name__ == "__main__":
    main()

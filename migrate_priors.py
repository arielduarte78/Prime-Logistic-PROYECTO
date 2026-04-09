import pandas as pd
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("Migrate_Priors")

backup_path = "data/parquet_db/stochastic_priors_backup.parquet"
edges_path = "data/parquet_db/edges.parquet"
output_path = "data/parquet_db/stochastic_priors.parquet"

def run_migration():
    logger.info("Cargando archivos parquet...")
    try:
        df_backup = pd.read_parquet(backup_path)
        df_edges = pd.read_parquet(edges_path)
    except FileNotFoundError as e:
        logger.error(f"Archivo no encontrado: {e}")
        sys.exit(1)

    logger.info(f"Backup histórico cargado con {len(df_backup)} registros.")
    
    # ─── RECREAR EL MAPEO u_rx, v_rx MAESTRO ───
    # En rustworkx los índices rx son posicionales respecto a unique_nodes
    unique_nodes = pd.unique(df_edges[['u', 'v']].values.ravel())
    
    # Creamos un DataFrame maestro de nodos para cumplir con el esquema (Merge/Join)
    df_nodes_master = pd.DataFrame({
        'osm_id': pd.Series(unique_nodes).astype(int),
        'rx_id': range(len(unique_nodes))
    })

    # ─── INYECCIÓN VÍA LEFT JOIN / MERGE ───
    logger.info("Realizando Left Join entre datos históricos y master...")
    
    # Asegurar tipos
    df_backup['u_osm'] = df_backup['u_osm'].astype(int)
    df_backup['v_osm'] = df_backup['v_osm'].astype(int)

    # 1. Join para u_rx
    df_merged = pd.merge(
        df_backup, 
        df_nodes_master, 
        left_on='u_osm', 
        right_on='osm_id', 
        how='left'
    ).rename(columns={'rx_id': 'u_rx'}).drop(columns=['osm_id'])

    # 2. Join para v_rx
    df_final = pd.merge(
        df_merged, 
        df_nodes_master, 
        left_on='v_osm', 
        right_on='osm_id', 
        how='left'
    ).rename(columns={'rx_id': 'v_rx'}).drop(columns=['osm_id'])

    # ─── LIMPIEZA ───
    rows_initial = len(df_final)
    df_final = df_final.dropna(subset=['u_rx', 'v_rx'])
    df_final['u_rx'] = df_final['u_rx'].astype(int)
    df_final['v_rx'] = df_final['v_rx'].astype(int)
    rows_after = len(df_final)

    if rows_initial != rows_after:
        logger.warning(f"Se descartaron {rows_initial - rows_after} registros huérfanos sin correspondencia OSM actual.")

    # Filtrar columnas
    stochastic_cols = [c for c in df_final.columns if c not in ['u_osm', 'v_osm', 'u_rx', 'v_rx']]
    df_final = df_final[['u_rx', 'v_rx'] + stochastic_cols]

    # ─── GUARDADO ───
    df_final.to_parquet(output_path, index=False)
    logger.info(f"Migración Completada. Guardados {rows_after} registros con el nuevo esquema en: {output_path}")

if __name__ == "__main__":
    run_migration()

#duckdb_ingestor.py
import time
import logging
from pathlib import Path
import duckdb
import pandas as pd

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("DuckDB_Ingestor")

# Resolve absolute path to edges.parquet dynamically
# __file__ refers to duckdb_ingestor.py
# parent -> bloque1
# parent.parent -> src
# parent.parent.parent -> Prime-Logistic-PROYECTO (Workspace Root)
EDGES_PARQUET_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "parquet_db" / "edges.parquet"
NODES_PARQUET_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "parquet_db" / "nodes.parquet"

def extract_subgraph_edges(h3_corridor: list[str]) -> pd.DataFrame:
    """
    Extracts edges from the immutable parquet dataset using DuckDB memory mapping,
    filtering only the requested H3 hexagons belonging to the spatial corridor.
    """
    start_time = time.time()
    
    if not h3_corridor:
        logger.warning("Empty H3 corridor provided. Returning empty DataFrame.")
        return pd.DataFrame()
        
    # Ensure all hexes are quoted for explicit SQL IN matching syntax.
    # Ex: tuple() generates ('hex',) for single items which breaks SQL syntax. 
    # Explicit SQL string formatting avoids this.
    in_clause_values = ", ".join([f"'{str(h)}'" for h in h3_corridor])
    
    # Construct exact query
    query = f"""
        SELECT u, v, length, highway, alpha_prior, beta_prior, h3_index_origin
        FROM read_parquet('{str(EDGES_PARQUET_PATH)}')
        WHERE h3_index_origin IN ({in_clause_values})
    """
    
    logger.info(f"Querying DuckDB for corridor mapped over {len(h3_corridor)} hexagons...")
    
    # DuckDB operates statelessly and extremely fast using memory mapped files.
    # We call .df() on the duckdb SQL interface to convert natively to Pandas.
    df_edges = duckdb.sql(query).df()
    
    elapsed_time = time.time() - start_time
    logger.info(f"DuckDB extraction complete in {elapsed_time:.3f} seconds. Extracted {len(df_edges)} edges.")
    
    return df_edges

def get_nearest_node_osm_id(lat: float, lon: float) -> int:
    # f-string SOLO para la ruta del archivo (estática)
    # ? para las coordenadas (dinámicas, parametrizadas)
    query = f"""
        SELECT osm_id,
               ((lat - ?) * (lat - ?) + (lon - ?) * (lon - ?)) AS dist_sq
        FROM read_parquet('{str(NODES_PARQUET_PATH)}')
        ORDER BY dist_sq ASC
        LIMIT 1
    """
    result = duckdb.execute(query, [lat, lat, lon, lon]).df()

    if result.empty:
        raise ValueError("No se encontró ningún nodo en nodes.parquet")
    return int(result.iloc[0]["osm_id"])

import os
import time
import logging
from pathlib import Path

import osmnx as ox
import pandas as pd
import h3
import pyarrow as pa
import pyarrow.parquet as pq

# ====================================================================
# Configuration & Setup
# ====================================================================

# Professional Logger Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ETL_H3_Builder")

# Target Municipalities (Qualified to ensure Overpass finds them in Argentina)
MUNICIPALITIES = [
    "CABA, Argentina",
    "Vicente López, Buenos Aires, Argentina",
    "San Isidro, Buenos Aires, Argentina",
    "Tigre, Buenos Aires, Argentina",
    "San Martín, Buenos Aires, Argentina",
    "Tres de Febrero, Buenos Aires, Argentina",
    "Morón, Buenos Aires, Argentina",
    "La Matanza, Buenos Aires, Argentina",
    "Avellaneda, Buenos Aires, Argentina",
    "Lanús, Buenos Aires, Argentina",
    "Lomas de Zamora, Buenos Aires, Argentina",
    "Quilmes, Buenos Aires, Argentina",
    "Ezeiza, Buenos Aires, Argentina"
]

# Mandatory Bounding Box (AMBA Region)
BBOX = {
    "north": -34.28,
    "south": -34.92,
    "east": -58.33,
    "west": -59.10
}

H3_RESOLUTION = 8

# Bayesian Priors Calibration Map (alpha, beta)
PRIOR_MAPPING = {
    "motorway": (95, 5),
    "trunk": (90, 10),
    "primary": (85, 15),
    "secondary": (75, 25),
    "tertiary": (65, 35),
    "residential": (50, 50),
    "track": (30, 70),
}
DEFAULT_PRIOR = (50, 50)

# OsmNx columns that are known to sometimes contain lists
LIST_COLUMNS_TO_STRING = ["highway", "lanes", "maxspeed", "access", "junction"]

OUTPUT_DIR = Path("data") / "parquet_db"

# ====================================================================
# Helper Functions
# ====================================================================

def get_priors(highway_val) -> tuple:
    """Returns the (alpha_prior, beta_prior) tuple depending on OSM highway classification."""
    hw_str = str(highway_val).lower()
    for kw, prior in PRIOR_MAPPING.items():
        if kw in hw_str:
            return prior
    return DEFAULT_PRIOR

# ====================================================================
# Main ETL Pipeline
# ====================================================================

def main():
    logger.info("==================================================")
    logger.info("STARTING PHASE 1: OFFLINE ETL - AMBA H3 SPATIAL COMPILATION")
    logger.info("==================================================")
    overall_start_time = time.time()
    
    # Ensure destination directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Critical step: Avoid timeouts on large Overpass API queries
    logger.info("Setting OSMnx timeout to 3000 seconds and using robust mirror")
    ox.settings.timeout = 3000
    ox.settings.overpass_url = "https://overpass.kumi.systems/api/interpreter"
    
    # ----------------------------------------------------------------
    # Stage 1: Download Graph
    # ----------------------------------------------------------------
    logger.info("--- STAGE 1: Downloading AMBA Drive Graph ---")
    stage1_start = time.time()
    
    try:
        logger.info(f"Attempting ox.graph_from_place with {len(MUNICIPALITIES)} municipalities")
        G = ox.graph_from_place(MUNICIPALITIES, network_type="drive")
        logger.info("Successfully downloaded graph using graph_from_place.")
    except Exception as e:
        logger.warning(f"graph_from_place failed or timed out: {e}")
        logger.warning(f"Mandatory Fallback triggered: Retrieving via ox.graph_from_bbox with BBOX: {BBOX}")
        try:
            # Compat: osmnx < 2.0 
            G = ox.graph_from_bbox(
                north=BBOX["north"],
                south=BBOX["south"],
                east=BBOX["east"],
                west=BBOX["west"],
                network_type="drive"
            )
        except TypeError:
            # Compat: osmnx >= 2.0 (Expects a `bbox` tuple as first/keyword argument: west, south, east, north)
            G = ox.graph_from_bbox(
                bbox=(BBOX["west"], BBOX["south"], BBOX["east"], BBOX["north"]),
                network_type="drive"
            )
        logger.info("Successfully downloaded graph using graph_from_bbox fallback.")
        
    logger.info(f"Stage 1 completed in {time.time() - stage1_start:.2f} seconds.")
    
    # ----------------------------------------------------------------
    # Stage 2: Convert to DataFrames
    # ----------------------------------------------------------------
    logger.info("--- STAGE 2: Converting Graph to DataFrames ---")
    stage2_start = time.time()
    
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(G)
    
    logger.info(f"Extracted Nodes: {len(gdf_nodes)}")
    logger.info(f"Extracted Edges: {len(gdf_edges)}")
    logger.info(f"Stage 2 completed in {time.time() - stage2_start:.2f} seconds.")
    
    # ----------------------------------------------------------------
    # Stage 3: Process Nodes & H3 Indexing
    # ----------------------------------------------------------------
    logger.info("--- STAGE 3: Processing Nodes and H3 Indexing ---")
    stage3_start = time.time()
    
    # Resolve the index if node ID is placed there by osmnx
    if "osmid" not in gdf_nodes.columns:
        gdf_nodes = gdf_nodes.reset_index()
    if "osmid" in gdf_nodes.columns:
        gdf_nodes = gdf_nodes.rename(columns={"osmid": "osm_id"})
        
    # Standardize coordinate column names internally
    if "y" in gdf_nodes.columns and "lat" not in gdf_nodes.columns:
        gdf_nodes = gdf_nodes.rename(columns={"y": "lat"})
    if "x" in gdf_nodes.columns and "lon" not in gdf_nodes.columns:
        gdf_nodes = gdf_nodes.rename(columns={"x": "lon"})
        
    # Calculate H3 index using latitude and longitude
    logger.info(f"Calculating H3 index (resolution {H3_RESOLUTION}) based on lat/lon...")
    try:
        # Standard API for h3-py <= 3.7.x
        gdf_nodes["h3_index"] = gdf_nodes.apply(
            lambda row: h3.geo_to_h3(row["lat"], row["lon"], H3_RESOLUTION), axis=1
        )
    except AttributeError:
        # Modern API for h3-py >= 4.0
        gdf_nodes["h3_index"] = gdf_nodes.apply(
            lambda row: h3.latlng_to_cell(row["lat"], row["lon"], H3_RESOLUTION), axis=1
        )
    
    # Deep cleaning: drop visual geometry to compress parquet
    if "geometry" in gdf_nodes.columns:
        gdf_nodes = gdf_nodes.drop(columns=["geometry"])
        logger.info("Removed 'geometry' column from Nodes DataFrame.")
        
    logger.info(f"Stage 3 completed in {time.time() - stage3_start:.2f} seconds.")
    
    # ----------------------------------------------------------------
    # Stage 4: Process Edges & Bayesian Priors Injection
    # ----------------------------------------------------------------
    logger.info("--- STAGE 4: Processing Edges and Bayesian Priors Injection ---")
    stage4_start = time.time()
    
    if "u" not in gdf_edges.columns or "v" not in gdf_edges.columns:
        gdf_edges = gdf_edges.reset_index()
        
    # Inherit h3_index from the source node (u)
    node_h3_map = gdf_nodes.set_index("osm_id")["h3_index"].to_dict()
    gdf_edges["h3_index_origin"] = gdf_edges["u"].map(node_h3_map)
    logger.info("Inherited 'h3_index_origin' from source nodes to edges.")
    
    # Calculate and Inject Bayesian Priors
    logger.info("Injecting Bayesian Priors based on 'highway' type...")
    priors = gdf_edges["highway"].apply(get_priors)
    gdf_edges["alpha_prior"] = priors.apply(lambda x: x[0])
    gdf_edges["beta_prior"] = priors.apply(lambda x: x[1])
    
    # Deep cleaning edges DataFrame
    if "geometry" in gdf_edges.columns:
        gdf_edges = gdf_edges.drop(columns=["geometry"])
        logger.info("Removed 'geometry' column from Edges DataFrame.")
        
    # Strict cleanup: converting problematic elements to strings for Parquet compatibility
    logger.info("Converting known list columns to string...")
    for col in LIST_COLUMNS_TO_STRING:
        if col in gdf_edges.columns:
            gdf_edges[col] = gdf_edges[col].astype(str)
            
    # Secondary generic fallback to guarantee typing sanity (prevent pa.ArrowInvalid)
    for col in gdf_edges.columns:
        if gdf_edges[col].apply(type).eq(list).any():
            gdf_edges[col] = gdf_edges[col].astype(str)
            logger.info(f"Auto-detected list formatting in column '{col}', converted to string.")
            
    logger.info(f"Stage 4 completed in {time.time() - stage4_start:.2f} seconds.")
    
    # ----------------------------------------------------------------
    # Stage 5: Export DataFrames to Parquet
    # ----------------------------------------------------------------
    logger.info("--- STAGE 5: Exporting Graph DataFrames to Parquet ---")
    stage5_start = time.time()
    
    nodes_parquet_path = OUTPUT_DIR / "nodes.parquet"
    edges_parquet_path = OUTPUT_DIR / "edges.parquet"
    
    logger.info(f"Writing nodes to {nodes_parquet_path}...")
    table_nodes = pa.Table.from_pandas(gdf_nodes)
    pq.write_table(table_nodes, nodes_parquet_path, compression="snappy")
    
    logger.info(f"Writing edges to {edges_parquet_path}...")
    table_edges = pa.Table.from_pandas(gdf_edges)
    pq.write_table(table_edges, edges_parquet_path, compression="snappy")
    
    # Size in MB
    nodes_mb = nodes_parquet_path.stat().st_size / (1024 * 1024)
    edges_mb = edges_parquet_path.stat().st_size / (1024 * 1024)
    logger.info(f"Final Nodes Parquet File Size: {nodes_mb:.2f} MB")
    logger.info(f"Final Edges Parquet File Size: {edges_mb:.2f} MB")
    logger.info(f"Stage 5 completed in {time.time() - stage5_start:.2f} seconds.")
    
    # ----------------------------------------------------------------
    # Stage 6: Export Bayesian Priors Lookup
    # ----------------------------------------------------------------
    logger.info("--- STAGE 6: Exporting Historical Priors Lookup ---")
    stage6_start = time.time()
    
    priors_historicos_path = OUTPUT_DIR / "priors_historicos.parquet"
    logger.info(f"Writing historical priors to {priors_historicos_path}...")
    
    # Create DataFrame from PRIOR_MAPPING and DEFAULT_PRIOR
    priors_records = [{"highway_type": k, "alpha_prior": v[0], "beta_prior": v[1]} for k, v in PRIOR_MAPPING.items()]
    priors_records.append({"highway_type": "default", "alpha_prior": DEFAULT_PRIOR[0], "beta_prior": DEFAULT_PRIOR[1]})
    df_priors = pd.DataFrame(priors_records)
    
    table_priors = pa.Table.from_pandas(df_priors)
    pq.write_table(table_priors, priors_historicos_path, compression="snappy")
    
    priors_mb = priors_historicos_path.stat().st_size / (1024 * 1024)
    logger.info(f"Final Priors Parquet File Size: {priors_mb:.4f} MB")
    logger.info(f"Stage 6 completed in {time.time() - stage6_start:.2f} seconds.")

    # ----------------------------------------------------------------
    # Finish
    # ----------------------------------------------------------------
    total_time = time.time() - overall_start_time
    logger.info("==================================================")
    logger.info(f"PHASE 1 ETL COMPLETED SUCCESSFULLY IN {total_time:.2f} SECONDS")
    logger.info("==================================================")

if __name__ == "__main__":
    main()

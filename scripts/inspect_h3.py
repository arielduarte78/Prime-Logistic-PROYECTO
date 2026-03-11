import pandas as pd
import h3
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "parquet_db"

df_edges = pd.read_parquet(str(DATA_DIR / "edges.parquet"))
df_nodes = pd.read_parquet(str(DATA_DIR / "nodes.parquet"))

h3_parent_func = getattr(h3, 'cell_to_parent', getattr(h3, 'h3_to_parent', None))

df_edges['h3_res4'] = df_edges['h3_index_origin'].apply(
    lambda x: h3_parent_func(x, 4) if pd.notna(x) else None
)
df_nodes['h3_res4'] = df_nodes['h3_index'].apply(
    lambda x: h3_parent_func(x, 4) if pd.notna(x) else None
)

with open(PROJECT_ROOT / "h3_macrozonas_out.txt", "w", encoding="utf-8") as f:
    f.write("=== MACRO-ZONAS H3 RES-4 (edges) ===\n")
    f.write(df_edges['h3_res4'].value_counts().to_string() + "\n")

    f.write("\n=== MACRO-ZONAS H3 RES-4 (nodes) ===\n")
    f.write(df_nodes['h3_res4'].value_counts().to_string() + "\n")

    f.write("\n=== NODOS POR MACRO-ZONA (muestra de OSM IDs) ===\n")
    for zona, grupo in df_nodes.groupby('h3_res4'):
        osm_sample = grupo['osm_id'].head(3).tolist()
        f.write(f"{zona}: {len(grupo)} nodos | sample: {osm_sample}\n")

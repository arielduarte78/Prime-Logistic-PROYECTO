import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "parquet_db"

df_nodes = pd.read_parquet(str(DATA_DIR / "nodes.parquet"))
df_edges = pd.read_parquet(str(DATA_DIR / "edges.parquet"))

print("=== NODES ===")
print(f"Total nodos: {len(df_nodes):,}")
print(f"Columnas: {df_nodes.columns.tolist()}")
print(df_nodes.head(5).to_string())

print("\n=== EDGES ===")
print(f"Total aristas: {len(df_edges):,}")
print(f"Columnas: {df_edges.columns.tolist()}")
print(df_edges.head(5).to_string())

print("\n=== HIGHWAY TYPES ===")
print(df_edges['highway'].value_counts().head(15).to_string())

print("\n=== H3 ZONES (sample) ===")
print(df_edges['h3_index_origin'].value_counts().head(10).to_string())

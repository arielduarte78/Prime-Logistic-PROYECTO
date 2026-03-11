import pandas as pd
from pathlib import Path

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 2000)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "parquet_db"

df_nodes = pd.read_parquet(str(DATA_DIR / "nodes.parquet"))
df_edges = pd.read_parquet(str(DATA_DIR / "edges.parquet"))

with open(PROJECT_ROOT / "parquet_report.txt", "w", encoding="utf-8") as f:
    f.write("=== NODES ===\n")
    f.write(f"Total nodos: {len(df_nodes):,}\n")
    f.write(f"Columnas: {df_nodes.columns.tolist()}\n")
    f.write(df_nodes.head(5).to_string() + "\n\n")

    f.write("=== EDGES ===\n")
    f.write(f"Total aristas: {len(df_edges):,}\n")
    f.write(f"Columnas: {df_edges.columns.tolist()}\n")
    f.write(df_edges.head(5).to_string() + "\n\n")

    f.write("=== HIGHWAY TYPES ===\n")
    f.write(df_edges['highway'].value_counts().head(15).to_string() + "\n\n")

    if 'h3_index' in df_edges.columns:
        f.write("=== H3 ZONES (sample) ===\n")
        f.write(df_edges['h3_index'].value_counts().head(10).to_string() + "\n")
    elif 'h3_index_origin' in df_edges.columns:
        f.write("=== H3 ZONES (sample) ===\n")
        f.write(df_edges['h3_index_origin'].value_counts().head(10).to_string() + "\n")

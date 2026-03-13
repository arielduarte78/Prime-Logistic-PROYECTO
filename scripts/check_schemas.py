import pandas as pd
import os

files = [
    'data/red_realista_argentina_arcs.parquet', 
    'data/red_realista_argentina_nodes.parquet', 
    'data/parquet_db/edges_backup.parquet', 
    'data/parquet_db/nodes.parquet'
]

output = []
for f in files:
    output.append(f"--- {f} ---")
    if not os.path.exists(f):
        output.append("File not found.")
        continue
    try:
        df = pd.read_parquet(f)
        output.append(f"Columns: {df.columns.tolist()}")
        output.append(f"Shape: {df.shape}")
        output.append(str(df.head(2)))
    except Exception as e:
        output.append(f"Error: {e}")
    output.append("-" * 20)

with open('schema_results.txt', 'w') as f_out:
    f_out.write('\n'.join(output))

print("Results written to schema_results.txt")

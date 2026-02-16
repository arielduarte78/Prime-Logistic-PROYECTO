import pandas as pd
import numpy as np
import os

os.makedirs("data", exist_ok=True)
file_path = "data/red_masiva_1000.xlsx"

# 10 Ciudades Estratégicas (1000 nodos total)
HUBS = [
    {"name": "CITY_1", "lat": -26.0, "lon": -65.0}, {"name": "CITY_2", "lat": -28.0, "lon": -60.0},
    {"name": "CITY_3", "lat": -30.0, "lon": -64.0}, {"name": "CITY_4", "lat": -32.0, "lon": -61.0},
    {"name": "CITY_5", "lat": -34.0, "lon": -59.0}, {"name": "CITY_6", "lat": -36.0, "lon": -62.0},
    {"name": "CITY_7", "lat": -38.0, "lon": -64.0}, {"name": "CITY_8", "lat": -41.0, "lon": -71.0},
    {"name": "CITY_9", "lat": -45.0, "lon": -68.0}, {"name": "CITY_10", "lat": -54.0, "lon": -68.0}
]

nodes_data, arcs_data = [], []
node_count, arc_count = 1, 1
city_hubs = []

for hub in HUBS:
    nodes_in_city = []
    for i in range(100):
        n_id = f"NODE_{node_count:04d}" # ID de nodo ok (4 dígitos)
        nodes_data.append({
            "id": n_id, "lat": round(hub["lat"] + np.random.uniform(-0.4, 0.4), 4),
            "lon": round(hub["lon"] + np.random.uniform(-0.4, 0.4), 4),
            "supply": 1000 if node_count == 1 else 0,
            "demand": 1000 if node_count == 1000 else 0,
            "proc_cost": 100 # Se mapeará en main.py
        })
        if i == 0:
            city_hubs.append(n_id)
        nodes_in_city.append(n_id)
        node_count += 1
    
    # Arcos locales
    for j in range(len(nodes_in_city)-1):
        # [CORRECCIÓN CRÍTICA] Usamos 04d para cumplir el formato ARC_XXXX
        arcs_data.append({
            "id": f"ARC_{arc_count:04d}", 
            "origin": nodes_in_city[j], "destination": nodes_in_city[j+1],
            "mode": "truck", "capacity": 5000, "cost": 0.1 
        })
        arc_count += 1

# Arcos troncales
for k in range(len(city_hubs)-1):
    arcs_data.append({
        "id": f"ARC_{arc_count:04d}", # [CORRECCIÓN CRÍTICA] 4 dígitos
        "origin": city_hubs[k], "destination": city_hubs[k+1],
        "mode": "truck", "capacity": 10000, "cost": 0.1
    })
    arc_count += 1

# EXPORTACIÓN
with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
    pd.DataFrame(nodes_data).to_excel(writer, sheet_name="NODES", index=False)
    pd.DataFrame(arcs_data).to_excel(writer, sheet_name="ARCS", index=False)

print(f"✅ Generados {len(nodes_data)} nodos y {len(arcs_data)} arcos con formato válido (ARC_XXXX).")
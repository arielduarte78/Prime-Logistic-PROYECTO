import pandas as pd
import numpy as np
import os

os.makedirs("data", exist_ok=True)

# 1. NODOS (Mantenemos tus 50 nodos realistas)
HUBS_CONFIG = [
    {"name": "TUCUMAN", "lat": -26.8, "lon": -65.2, "count": 12, "role": "producer"},
    {"name": "CORDOBA", "lat": -31.4, "lon": -64.2, "count": 13, "role": "transit"},
    {"name": "ROSARIO", "lat": -32.9, "lon": -60.6, "count": 12, "role": "port_transit"},
    {"name": "BSAS",    "lat": -34.6, "lon": -58.4, "count": 13, "role": "consumer"}
]

nodes_data = []
node_ids_by_city = {}
global_counter = 1

for hub in HUBS_CONFIG:
    city_nodes = []
    for i in range(hub["count"]):
        n_id = f"NODE_{global_counter:04d}"
        city_nodes.append(n_id)
        lat = hub["lat"] + np.random.uniform(-0.3, 0.3)
        lon = hub["lon"] + np.random.uniform(-0.3, 0.3)
        
        nodes_data.append({
            "id": n_id,
            "lat": round(lat, 4), "lon": round(lon, 4),
            "station_type": "airport" if i == 0 else "warehouse",
            "supply": np.random.randint(400, 600) if hub["role"] == "producer" else 0,
            "demand": np.random.randint(400, 600) if hub["role"] == "consumer" else 0,
            "proc_cost": np.random.randint(60, 100) if hub["role"] == "producer" else np.random.randint(200, 350)
        })
        global_counter += 1
    node_ids_by_city[hub["name"]] = city_nodes

# 2. ARCOS (Garantizando el flujo)
arcs_data = []
arc_count = 1

cities = ["TUCUMAN", "CORDOBA", "ROSARIO", "BSAS"]

for idx, city in enumerate(cities):
    nodes = node_ids_by_city[city]
    # Conexión en cadena interna (1->2, 2->3...)
    for i in range(len(nodes) - 1):
        arcs_data.append({
            "id": f"ARC_{arc_count:04d}",
            "origin": nodes[i], "destination": nodes[i+1],
            "mode": "truck", "capacity": 1500, "cost": round(np.random.uniform(40, 100), 2)
        })
        arc_count += 1
    
    # CONEXIÓN BACKBONE (El último de esta ciudad al primero de la que sigue)
    if idx < len(cities) - 1:
        next_city_nodes = node_ids_by_city[cities[idx+1]]
        arcs_data.append({
            "id": f"ARC_{arc_count:04d}",
            "origin": nodes[-1], # Último de la ciudad actual
            "destination": next_city_nodes[0], # Primero de la siguiente
            "mode": "truck", "capacity": 3000, "cost": round(np.random.uniform(600, 1000), 2)
        })
        arc_count += 1

# 3. ATAJO AÉREO (Tucumán a BSAS)
arcs_data.append({
    "id": "ARC_9999",
    "origin": node_ids_by_city["TUCUMAN"][0],
    "destination": node_ids_by_city["BSAS"][0],
    "mode": "air", "capacity": 1000, "cost": 7500.0
})

# EXPORTAR
df_nodes = pd.DataFrame(nodes_data)
df_arcs = pd.DataFrame(arcs_data)
with pd.ExcelWriter("data/red_tesis_50_nodos.xlsx") as writer:
    df_nodes.to_excel(writer, sheet_name="NODES", index=False)
    df_arcs.to_excel(writer, sheet_name="ARCS", index=False)

print("✅ Red 'Backbone' de 50 nodos generada exitosamente.")
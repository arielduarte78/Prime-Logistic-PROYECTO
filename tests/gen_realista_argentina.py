import pandas as pd
import numpy as np
import os

# Configuración de Archivo Nuevo
os.makedirs("data", exist_ok=True)
FILE_NAME = "red_realista_argentina.xlsx"
file_path = os.path.join("data", FILE_NAME)

# 1. CONFIGURACIÓN GEOGRÁFICA REAL (Lat/Lon aproximadas de Argentina)
# Simulamos 10 Centros de Distribución Regionales
HUBS = [
    {"name": "JUJUY",       "lat": -24.18, "lon": -65.29},
    {"name": "TUCUMAN",     "lat": -26.80, "lon": -65.21},
    {"name": "CORDOBA",     "lat": -31.42, "lon": -64.18},
    {"name": "ROSARIO",     "lat": -32.94, "lon": -60.63},
    {"name": "MENDOZA",     "lat": -32.88, "lon": -68.83},
    {"name": "BSAS_N",      "lat": -34.50, "lon": -58.50}, # AMBA Norte
    {"name": "BSAS_S",      "lat": -34.80, "lon": -58.40}, # AMBA Sur
    {"name": "BAHIA",       "lat": -38.71, "lon": -62.26},
    {"name": "COMODORO",    "lat": -45.86, "lon": -67.50},
    {"name": "USHUAIA",     "lat": -54.80, "lon": -68.30}
]

nodes_data = []
arcs_data = []
node_counter = 1
arc_counter = 1
hub_ids = []

# --- GENERACIÓN DE NODOS (10 Ciudades x 100 Nodos = 1000 Nodos) ---
print("📍 Generando geografía realista...")

for region in HUBS:
    city_nodes = []
    # El primer nodo de cada región es el HUB (Aeropuerto/Centro Logístico)
    for i in range(100):
        n_id = f"NODE_{node_counter:04d}"
        
        # Dispersión geográfica: Los nodos locales están a +/- 0.3 grados (~30km) del Hub
        # Esto simula el área metropolitana de cada ciudad.
        lat_offset = np.random.uniform(-0.3, 0.3)
        lon_offset = np.random.uniform(-0.3, 0.3)
        
        # Si es el Hub (i==0), usamos coordenadas exactas
        real_lat = region["lat"] if i == 0 else region["lat"] + lat_offset
        real_lon = region["lon"] if i == 0 else region["lon"] + lon_offset

        nodes_data.append({
            "id": n_id,
            "lat": round(real_lat, 6), # Mayor precisión para Haversine
            "lon": round(real_lon, 6),
            "station_type": "airport" if i == 0 else "warehouse", # Para metadata
            "proc_cost": np.random.randint(150, 500), # Costo operativo de nodo ($150-$500)
            "supply": 5000 if node_counter == 1 else 0, # Inicio en Jujuy
            "demand": 5000 if node_counter == 1000 else 0 # Fin en Ushuaia
        })
        
        if i == 0:
            hub_ids.append(n_id)
        city_nodes.append(n_id)
        node_counter += 1

    # --- ARCOS INTRA-CIUDAD (Última Milla) ---
    # Conectamos los nodos locales en cadena para garantizar flujo interno
    for j in range(len(city_nodes) - 1):
        arcs_data.append({
            "id": f"ARC_{arc_counter:04d}",
            "origin": city_nodes[j],
            "destination": city_nodes[j+1],
            "mode": "truck",
            "capacity": 2000,
            "cost": 0.0 # <--- IMPORTANTE: 0.0 activa el cálculo por distancia real
        })
        arc_counter += 1

# --- ARCOS INTER-CIUDAD (Troncal / Backbone) ---
# Conectamos los Hubs de norte a sur (Jujuy -> Tucumán -> ... -> Ushuaia)
for k in range(len(hub_ids) - 1):
    arcs_data.append({
        "id": f"ARC_{arc_counter:04d}",
        "origin": hub_ids[k],
        "destination": hub_ids[k+1],
        "mode": "truck",
        "capacity": 20000, # Alta capacidad en ruta
        "cost": 0.0 # <--- Se calculará distancia (ej: 800km * $2.5)
    })
    arc_counter += 1

# --- EL UNICORNIO (Puente Aéreo Directo) ---
# De Jujuy (Hub 1) directo a Ushuaia (Hub 10)
arcs_data.append({
    "id": f"ARC_{arc_counter:04d}",
    "origin": hub_ids[0],
    "destination": hub_ids[-1],
    "mode": "air", # <--- Tarifa mucho más cara ($18.0) pero distancia recta
    "capacity": 5000,
    "cost": 0.0 
})

# EXPORTACIÓN
with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
    pd.DataFrame(nodes_data).to_excel(writer, sheet_name="NODES", index=False)
    pd.DataFrame(arcs_data).to_excel(writer, sheet_name="ARCS", index=False)

print(f"✅ EXITO: Red Realista generada en '{file_path}'")
print(f"   - Nodos: {len(nodes_data)}")
print(f"   - Arcos: {len(arcs_data)}")
print("   - Costos en Excel: 0.0 (El sistema usará Haversine * Tarifa)")
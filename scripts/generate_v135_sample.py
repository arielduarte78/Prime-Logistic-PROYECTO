#!/usr/bin/env python3
"""
generate_v135_sample.py — Generador de datos de prueba V1.3.5
Genera data/realistic_network_v135.xlsx con tabs NODES y FLEET.
"""
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT   = os.path.join(DATA_DIR, "realistic_network_v135.xlsx")

# ─────────────────────────────────────────────────────────────
# NODES — 6 nodos reales de Argentina
# ─────────────────────────────────────────────────────────────
nodes = pd.DataFrame([
    {"id": "BA_WAREHOUSE",  "lat": -34.6037, "lon": -58.3816, "station_type": "warehouse",
     "supply": 50000, "demand": 0,     "proc_cost": 120.0},
    {"id": "BA_TERMINAL",   "lat": -34.5750, "lon": -58.4160, "station_type": "terminal",
     "supply": 0,     "demand": 0,     "proc_cost": 80.0},
    {"id": "ROSARIO_CLIENT","lat": -32.9468, "lon": -60.6393, "station_type": "client",
     "supply": 0,     "demand": 18000, "proc_cost": 0.0},
    {"id": "CORDOBA_CLIENT","lat": -31.4201, "lon": -64.1888, "station_type": "client",
     "supply": 0,     "demand": 12000, "proc_cost": 0.0},
    {"id": "MDP_WAREHOUSE", "lat": -38.0055, "lon": -57.5426, "station_type": "warehouse",
     "supply": 30000, "demand": 0,     "proc_cost": 95.0},
    {"id": "MENDOZA_CLIENT","lat": -32.8895, "lon": -68.8458, "station_type": "client",
     "supply": 0,     "demand": 8000,  "proc_cost": 0.0},
])

# ─────────────────────────────────────────────────────────────
# FLEET — 3 vehículos con parámetros realistas
# ─────────────────────────────────────────────────────────────
fleet = pd.DataFrame([
    {
        "vehicle_id": "TRUCK_01",
        "mode": "truck",
        "capacity": 28000,
        "cost_per_km": 1.85,
        "max_range_km": 1200,
        "allowed_stations": "warehouse,client,terminal",
        "count": 5,
    },
    {
        "vehicle_id": "CAR_01",
        "mode": "car",
        "capacity": 800,
        "cost_per_km": 0.45,
        "max_range_km": 600,
        "allowed_stations": "warehouse,client",
        "count": 10,
    },
    {
        "vehicle_id": "BUS_01",
        "mode": "bus",
        "capacity": 4000,
        "cost_per_km": 1.10,
        "max_range_km": 900,
        "allowed_stations": "terminal,warehouse,client",
        "count": 3,
    },
])

# ─────────────────────────────────────────────────────────────
# Escritura
# ─────────────────────────────────────────────────────────────
os.makedirs(DATA_DIR, exist_ok=True)

with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
    nodes.to_excel(writer, sheet_name="NODES", index=False)
    fleet.to_excel(writer, sheet_name="FLEET", index=False)

print(f"[OK] Archivo generado: {OUTPUT}")
print(f"     NODES: {len(nodes)} registros")
print(f"     FLEET: {len(fleet)} registros")

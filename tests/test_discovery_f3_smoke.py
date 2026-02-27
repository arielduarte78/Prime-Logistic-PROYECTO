"""Smoke test for Phase 3: Discovery Engine with SmartLazyIngestor (F3)."""
import sys, logging
import os
import shutil

sys.path.insert(0, "src")
logging.basicConfig(level=logging.INFO)

from bloque1.models import NodeRecord
from bloque1.fleet_schema import FleetVehicle
from bloque1.discovery_engine import DiscoveryEngine
from bloque1.smart_ingestor import SmartLazyIngestor
from bloque1.config import H3RouterConfig
from bloque1.cache_manager import SafeCacheManager

# Usamos un repo de cache temporal para la prueba
test_cache_dir = "tests/temp_h3_cache_f3"
os.makedirs(test_cache_dir, exist_ok=True)

# 1. Setup Ingestor
config = H3RouterConfig(resolution=5, buffer_rings=0, local_rings=0)
cache_manager = SafeCacheManager(cache_dir=test_cache_dir)
ingestor = SmartLazyIngestor(config, cache_manager)

# 2. Setup Nodes & Fleet (Escenario controlado pequeño para no saturar OSM)
nodes = [
    # Nodos muy cercanos en Buenos Aires para asegurar éxito rápido de OSMnx
    NodeRecord(id="NODE_O1", lat=-34.6037, lon=-58.3816, station_type="warehouse"), # Obelisco
    NodeRecord(id="NODE_D1", lat=-34.6060, lon=-58.3810, station_type="warehouse"), # Pocas cuadras
    NodeRecord(id="NODE_D2", lat=-34.5880, lon=-58.3980, station_type="warehouse"), # Recoleta
]

fleet = [
    FleetVehicle(
        mode="car", capacity=2.0, cost_per_km=1.0, max_range_km=50.0, # Rango corto para probar F3 discarding
        allowed_stations=["warehouse"],
        vehicle_id="CAR_01",
    ),
    FleetVehicle(
        mode="truck", capacity=20.0, cost_per_km=3.0, max_range_km=1000.0,
        allowed_stations=["warehouse"],
        vehicle_id="TRUCK_01",
    )
]

# 3. Ejecutar Motor
engine = DiscoveryEngine(nodes, fleet)

# F1 & F2
candidates_f12, telemetry = engine.run_filters_1_2()

print(f"\nCandidates survived F1/F2: {len(candidates_f12)}")

# F3 (Physical Validation)
csv_out = "tests/test_audit_output.csv"
candidates_f3 = engine.run_filter_3(candidates_f12, ingestor, telemetry, output_csv=csv_out)

print(f"\nCandidates survived F3: {len(candidates_f3)}")

# 4. Validaciones
print("\n--- Telemetría ---")
print(telemetry.summary())

assert os.path.exists(csv_out), "CSV Audit file not created!"

# Cleanup
if os.path.exists(test_cache_dir):
    shutil.rmtree(test_cache_dir, ignore_errors=True)

print("PHASE 3 SMOKE TEST COMPLETED.")

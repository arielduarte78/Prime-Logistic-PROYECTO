"""Smoke test for Phase 2: Discovery Engine Filters 1 & 2."""
import sys, logging
sys.path.insert(0, "src")
logging.basicConfig(level=logging.INFO)

from bloque1.models import NodeRecord
from bloque1.fleet_schema import FleetVehicle
from bloque1.discovery_engine import DiscoveryEngine

# --- 5 nodos en Argentina, 2 vehiculos ---
nodes = [
    NodeRecord(id="NODE_0001", lat=-34.60, lon=-58.38, station_type="warehouse"),
    NodeRecord(id="NODE_0002", lat=-31.42, lon=-64.18, station_type="factory"),
    NodeRecord(id="NODE_0003", lat=-32.94, lon=-60.65, station_type="warehouse"),
    NodeRecord(id="NODE_0004", lat=-38.00, lon=-57.55, station_type="terminal"),
    NodeRecord(id="NODE_0005", lat=-26.83, lon=-65.20, station_type="client"),
]

fleet = [
    FleetVehicle(
        mode="truck", capacity=30.0, cost_per_km=2.5, max_range_km=1200.0,
        allowed_stations=["warehouse", "factory", "terminal"],
        vehicle_id="FLEET_TRUCK_01",
    ),
    FleetVehicle(
        mode="car", capacity=2.0, cost_per_km=1.0, max_range_km=500.0,
        allowed_stations=["warehouse", "client"],
        vehicle_id="FLEET_CAR_01",
    ),
]

engine = DiscoveryEngine(nodes, fleet)
candidates, telemetry = engine.run_filters_1_2()

print()
print(f"Candidates found: {len(candidates)}")
for c in candidates:
    print(f"  {c.origin.id} -> {c.destination.id}  [{c.vehicle.vehicle_id}]  {c.estimated_distance_km:.0f} km")

print()
print(f"Telemetry:")
print(f"  Total input:      {telemetry.total_input_pairs}")
print(f"  F1 survivors:     {telemetry.filter_1_survivors}")
print(f"  F2 survivors:     {telemetry.filter_2_survivors}")
print(f"  Vehicles:         {telemetry.vehicles_processed}")
print()

# --- Assertions ---
assert telemetry.total_input_pairs == 5 * 4 * 2, f"Expected {5*4*2}, got {telemetry.total_input_pairs}"
assert telemetry.filter_1_survivors == 12 + 6, f"Expected 18, got {telemetry.filter_1_survivors}"
assert telemetry.filter_2_survivors > 0, "Expected some F2 survivors"
assert telemetry.filter_2_survivors <= telemetry.filter_1_survivors, "F2 <= F1"
assert all(c.estimated_distance_km > 0 for c in candidates), "All distances > 0"
assert telemetry.total_time_ms > 0, "Total time > 0"

# Car max_range=500km. Buenos Aires-Tucuman ~1200km. Should NOT survive F2.
car_ba_tuc = [c for c in candidates if c.origin.id == "NODE_0001" and c.destination.id == "NODE_0005"]
assert len(car_ba_tuc) == 0, "BA-Tucuman car should be filtered by range"

# Truck max_range=1200. Buenos Aires-Rosario ~300km. SHOULD survive F2.
truck_ba_ros = [c for c in candidates if c.origin.id == "NODE_0001" and c.destination.id == "NODE_0003" and c.vehicle.mode == "truck"]
assert len(truck_ba_ros) == 1, "BA-Rosario truck should survive"

# Verify BA-Rosario distance is reasonable (roughly 280-310 km Haversine)
ba_ros_dist = truck_ba_ros[0].estimated_distance_km
assert 250 < ba_ros_dist < 350, f"BA-Rosario distance should be ~300km, got {ba_ros_dist:.0f}"

# Node 5 (client) should NEVER appear in truck candidates (not in truck allowed_stations)
truck_client = [c for c in candidates if c.vehicle.mode == "truck" and (c.origin.station_type == "client" or c.destination.station_type == "client")]
assert len(truck_client) == 0, "Truck should not connect to client nodes"

print("ALL PHASE 2 ASSERTIONS PASSED")

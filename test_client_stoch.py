import logging
import asyncio
from fastapi.testclient import TestClient
from main import app

logging.basicConfig(level=logging.INFO)

payload = {
    "vehicles": [
        {"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 5.0, "max_shift_minutes": 480},
        {"id": "v2", "origin_lat": -34.6137, "origin_lon": -58.3916, "capacity_tons": 5.0, "max_shift_minutes": 480}
    ],
    "destinations": [
        {"id": "d1", "lat": -34.6237, "lon": -58.4016, "demand_tons": 1.0, "service_time_min": 10},
        {"id": "d2", "lat": -34.6337, "lon": -58.4116, "demand_tons": 1.0, "service_time_min": 10},
        {"id": "d3", "lat": -34.6437, "lon": -58.4216, "demand_tons": 1.0, "service_time_min": 10},
        {"id": "d4", "lat": -34.6537, "lon": -58.4316, "demand_tons": 1.0, "service_time_min": 10}
    ],
    "time_limit_seconds": 15,
    "stochastic_mode": True,
    "allowed_archetypes": ["equilibrista"]
}
try:
    with TestClient(app) as client:
        response = client.post("/fleet", json=payload)
        print("STATUS", response.status_code)
except Exception as e:
    import traceback
    traceback.print_exc()

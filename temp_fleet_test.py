import requests
import json
import sys

BASE = "http://localhost:8000/fleet"
HEADERS = {"X-API-Key": "dev_key_123", "Content-Type": "application/json"}
PAYLOAD = {
    "vehicles": [
        {"id": "V1", "capacity_tons": 5.0, "origin_lat": -34.6037, "origin_lon": -58.3816}
    ],
    "destinations": [
        {"id": "D1", "demand_tons": 2.0, "lat": -34.4500, "lon": -58.5500}
    ],
    "departure_time": "08:00",
    "allowed_archetypes": ["apostador"]
}

try:
    r = requests.post(BASE, json=PAYLOAD, headers=HEADERS, timeout=180)
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")

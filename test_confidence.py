import requests
import json

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

r = requests.post(BASE, json=PAYLOAD, headers=HEADERS, timeout=180)
data = r.json()

if "plans" in data and "apostador" in data["plans"]:
    segs = data["plans"]["apostador"].get("segments_pareto", [])
    if segs:
        for sol in segs[0].get("pareto_solutions", []):
            print(f"Archetype: {sol['archetype']:<15} w_survival: {sol['w_survival']:.4f} -> confidence: {sol['confidence']:.1f}")

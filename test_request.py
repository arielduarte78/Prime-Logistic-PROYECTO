import requests
import time

url = "http://127.0.0.1:8010/route"
payload = {
  "vehicles": [
    {
      "id": "truck1",
      "capacity_tons": 10.0,
      "origin_lat": -34.640989,
      "origin_lon": -58.526270
    }
  ],
  "destinations": [
    {
      "id": "dest1",
      "demand_tons": 5.0,
      "lat": -34.707141,
      "lon": -58.503348
    }
  ],
  "risk_profile": "balanced",
  "economic_profile": {
    "c_km_ars": 2000.0,
    "c_hora_ars": 50000.0,
    "ausa_25_mayo_ars": 9000.0
  }
}

try:
    response = requests.post(url, json=payload, timeout=30)
    print(f"Status: {response.status_code}")
    print(response.json())
except Exception as e:
    print(f"Error: {e}")

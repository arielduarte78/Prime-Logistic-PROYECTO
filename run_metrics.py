import requests
import json
import time

payload = {
  "vehicles": [
    {
      "id": "Camion_Norte",
      "capacity_tons": 10.0,
      "origin_lat": -34.5422,
      "origin_lon": -58.4633
    },
    {
      "id": "Camion_Sur",
      "capacity_tons": 5.0,
      "origin_lat": -34.6511,
      "origin_lon": -58.3744
    }
  ],
  "destinations": [
    {
      "id": "Cliente_Palermo",
      "demand_tons": 4.0,
      "lat": -34.5888,
      "lon": -58.4305
    },
    {
      "id": "Cliente_Avellaneda",
      "demand_tons": 3.0,
      "lat": -34.6622,
      "lon": -58.3655
    },
    {
      "id": "Cliente_Lanus",
      "demand_tons": 2.0,
      "lat": -34.7000,
      "lon": -58.3900
    }
  ],
  "allowed_archetypes": ["tanque", "apostador"],
  "time_limit_seconds": 5,
  "economic_profile": {
    "c_hora_ars": 85000.0,
    "ausa_25_mayo_ars": 12000.0
  }
}

try:
    print("Enviando request a /fleet...")
    response = requests.post("http://127.0.0.1:8000/fleet", json=payload)
    print(f"Status: {response.status_code}")
    data = response.json()
    
    print("\n--- METRICAS ---")
    print(f"Nodos en subgrafo (Fase 1): {data.get('subgraph_edges')}")
    print(f"Total time ms: {data.get('total_time_ms'):.2f} ms")
    
    for archetype, plan in data.get("plans", {}).items():
        metrics = plan.get("metrics", {})
        print(f"\nArquetipo: {archetype}")
        print(f"  Phase 2 Time (Matriz Rustworkx): {metrics.get('phase2_time_ms', 0):.2f} ms")
        print(f"  Phase 3 Time (OR-Tools solver): {metrics.get('phase3_time_ms', 0):.2f} ms")
        
except Exception as e:
    print(f"Error: {e}")

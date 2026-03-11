import requests

payload = {
    "vehicles": [{"id": "V1", "capacity_tons": 10.0, "origin_lat": -34.6037, "origin_lon": -58.3816}],
    "destinations": [{"id": "D1", "demand_tons": 5.0, "lat": -34.5200, "lon": -58.4500}]
}
headers = {"X-API-Key": "dev_key_123"}

r = requests.post("http://localhost:8000/route", json=payload, headers=headers)
data = r.json()

for sol in data.get("pareto_solutions", []):
    coords = sol.get("route_coordinates", [])
    print(f"Arquetipo {sol['archetype']}: {len(coords)} coordenadas extraídas.")
    if coords:
        print(f"  Primer punto: {coords[0]}")
        print(f"  Último punto: {coords[-1]}")
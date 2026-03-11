import subprocess
import time
import requests

server = subprocess.Popen(["c:/Users/Usuario/Prime-Logistic-PROYECTO/venv/Scripts/python.exe", "-m", "uvicorn", "src.api.main:app", "--port", "8000"])
time.sleep(15)

payload = {
    "vehicles": [{"id": "V1", "capacity_tons": 10.0, "origin_lat": -34.6037, "origin_lon": -58.3816}],
    "destinations": [{"id": "D1", "demand_tons": 5.0, "lat": -34.5200, "lon": -58.4500}]
}
headers = {"X-API-Key": "dev_key_123"}

try:
    r = requests.post("http://localhost:8000/route", json=payload, headers=headers)
    print("Status code:", r.status_code)
    
    data = r.json()
    if r.status_code == 200:
        for sol in data.get("pareto_solutions", []):
            coords = sol.get("route_coordinates", [])
            print(f"Arquetipo {sol['archetype']}: {len(coords)} coordenadas extraidas.")
            if coords:
                print(f"  Primer punto: {coords[0]}")
                print(f"  Ultimo punto: {coords[-1]}")
    else:
        print("Response:", r.text)
except Exception as e:
    print("Error:", e)
finally:
    server.terminate()

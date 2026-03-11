import time
import requests

route_payload = {
    "stochastic_mode": False,
    "vehicles": [{"id": "V1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 5.0}],
    "destinations": [{"id": "D1", "lat": -34.7000, "lon": -58.4000, "demand_tons": 2.0}],
    "allowed_archetypes": ["tanque", "equilibrista"]
}

try:
    print('=== Request 1 ===')
    t0 = time.time()
    r1 = requests.post('http://127.0.0.1:8019/route', json=route_payload, headers={'x-api-key': 'dev_key_123'}, timeout=60)
    print(f'/route res1 en {time.time() - t0:.3f}s con status {r1.status_code}')

    print('\n=== Request 2 ===')
    t1 = time.time()
    r2 = requests.post('http://127.0.0.1:8019/route', json=route_payload, headers={'x-api-key': 'dev_key_123'}, timeout=60)
    print(f'/route res2 en {time.time() - t1:.3f}s con status {r2.status_code}')
except Exception as e:
    print(f'Error: {e}')

import sys
import time
import requests

def test_routes():
    # Carga util VRP (fleet)
    fleet_payload = {
      "stochastic_mode": False,
      "time_limit_seconds": 10,
      "vehicles": [
        {
          "id": "V1",
          "origin_lat": -34.6037,
          "origin_lon": -58.3816,
          "capacity_tons": 5.0
        }
      ],
      "destinations": [
        {
          "id": "D1",
          "lat": -34.7000,
          "lon": -58.4000,
          "demand_tons": 2.0
        }
      ],
      "allowed_archetypes": ["tanque", "equilibrista"]
    }
    
    # Carga util Routing
    route_payload = {
      "stochastic_mode": False,
      "vehicles": [
        {
          "id": "V1",
          "origin_lat": -34.6037,
          "origin_lon": -58.3816,
          "capacity_tons": 5.0
        }
      ],
      "destinations": [
        {
          "id": "D1",
          "lat": -34.7000,
          "lon": -58.4000,
          "demand_tons": 2.0
        }
      ]
    }

    try:
        t0 = time.time()
        print('Testing /fleet...')
        r1 = requests.post('http://127.0.0.1:8019/fleet', json=fleet_payload, headers={'X-API-Key': 'prime-admin-key'}, timeout=60)
        t_fleet = time.time() - t0
        print(f'/fleet respondio en {t_fleet:.3f}s con status {r1.status_code}')
        
        t1 = time.time()
        print('\nTesting /route...')
        r2 = requests.post('http://127.0.0.1:8019/route', json=route_payload, headers={'X-API-Key': 'prime-admin-key'}, timeout=40)
        t_route = time.time() - t1
        print(f'/route respondio en {t_route:.3f}s con status {r2.status_code}')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    test_routes()

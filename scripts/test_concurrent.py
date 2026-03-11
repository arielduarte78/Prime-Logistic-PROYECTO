import sys
import time
import requests
import threading

def test_concurrency():
    # Wait for the background server to fully start
    for i in range(20):
        try:
            r = requests.get('http://127.0.0.1:8019/', timeout=1)
            break
        except requests.exceptions.ConnectionError:
            time.sleep(1)
            continue
            
    print('Testing /route vs / concurrency...')
    payload = {
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
      ],
      "allowed_archetypes": ["tanque", "equilibrista"]
    }
    
    def run_slow_request():
        try:
            print(f'[{time.strftime("%H:%M:%S")}] Disparando request a /route (pesado)...')
            res = requests.post('http://127.0.0.1:8019/route', json=payload, headers={'X-API-Key': 'prime-admin-key'}, timeout=60)
            print(f'[{time.strftime("%H:%M:%S")}] /route respondio con status {res.status_code}')
        except Exception as e:
            print(f'Error en /route: {e}')

    t = threading.Thread(target=run_slow_request)
    t.start()
    
    time.sleep(1.0)
    
    print(f'[{time.strftime("%H:%M:%S")}] Disparando request concurrente a / (healthcheck)...')
    t_start = time.time()
    try:
        r2 = requests.get('http://127.0.0.1:8019/', timeout=2)
        elapsed = time.time() - t_start
        print(f'[{time.strftime("%H:%M:%S")}] / respondio en {elapsed:.3f}s con status {r2.status_code}')
        if elapsed < 1.0:
            print('[OK] Concurrencia EXITOSA! El servidor no esta bloqueado.')
        else:
            print('[WARN] Concurrencia lenta. Posible bloqueo.')
    except Exception as e:
        print(f'[ERROR] Concurrencia FALLIDA. El timeout ocurrio: {e}')
        
    t.join()

if __name__ == '__main__':
    test_concurrency()

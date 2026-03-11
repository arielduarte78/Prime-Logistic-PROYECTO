import sys
import time
import requests
import threading
import subprocess

def test_concurrency():
    print('Arrancando servidor uvicorn...')
    # Iniciar servidor
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'src.api.main:app', '--port', '8019'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    # Esperar a que levante
    started = False
    for i in range(60):
        time.sleep(1)
        try:
            r = requests.get('http://127.0.0.1:8019/', timeout=1)
            started = True
            break
        except requests.exceptions.ConnectionError:
            continue
            
    if not started:
        print('El servidor no arranco.')
        server.terminate()
        print('Salida del servidor:')
        print(server.stdout.read())
        return

    print('Servidor arrancado y respondiendo.')
    
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
    
    slow_done = False
    
    def run_slow_request():
        nonlocal slow_done
        try:
            print(f'[{time.strftime("%H:%M:%S")}] Disparando request a /route (pesado)...')
            res = requests.post('http://127.0.0.1:8019/route', json=payload, headers={'X-API-Key': 'prime-admin-key'}, timeout=40)
            print(f'[{time.strftime("%H:%M:%S")}] /route respondio con status {res.status_code}')
        except Exception as e:
            print(f'Error en /route: {e}')
        finally:
            slow_done = True

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
    
    server.terminate()
    print('Prueba finalizada.')

if __name__ == '__main__':
    test_concurrency()

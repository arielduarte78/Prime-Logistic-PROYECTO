import asyncio
import aiohttp
import time

API_URL = "http://localhost:8000/route"

# PAYLOAD PARA CRUCE DE FRONTERA (Retiro -> Lanús)
PAYLOAD = {
    "vehicles": [{
        "id": "CAMION-PRO-01",
        "capacity_tons": 30.0,
        "origin_lat": -34.5912,  # Retiro (Terminal)
        "origin_lon": -58.3735
    }],
    "destinations": [{
        "id": "CENTRO-DIST-LANUS",
        "demand_tons": 20.0,
        "lat": -34.7050,         # Lanús (Centro)
        "lon": -58.3950
    }]
}

async def fetch_route(session, request_id):
    print(f"[Req {request_id}] Disparando petición...")
    start = time.time()
    try:
        async with session.post(API_URL, json=PAYLOAD) as response:
            status = response.status
            data = await response.json()
            elapsed = time.time() - start
            
            if status == 200:
                archetypes = ", ".join(f"{s['archetype'].upper()} ({s['confidence']:.4f})" for s in data['pareto_solutions'])
                print(f"✅ [Req {request_id}] HTTP 200 | {elapsed:.2f}s | Edges: {data['total_edges']} | {archetypes}")
            elif status == 429:
                print(f"🛑 [Req {request_id}] HTTP 429 | BLOQUEADO POR SEMÁFORO (Fail-Fast Exitoso)")
            else:
                print(f"❌ [Req {request_id}] HTTP {status} | Error: {data}")
    except Exception as e:
         print(f"⚠️ [Req {request_id}] Fallo de conexión: {e}")

async def main():
    print("==================================================")
    print(" INICIANDO TEST DE ESTRÉS CONCURRENTE (5 REQUESTS)")
    print("==================================================")
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_route(session, i) for i in range(1, 6)]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
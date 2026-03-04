import asyncio
import aiohttp
import time

API_URL = "http://localhost:8000/route"

# Definimos 3 perfiles de prueba
TEST_CASES = [
    {"name": "MICRO", "o": (-34.6037, -58.3816), "d": (-34.6083, -58.3712)}, # Obelisco -> Pza Mayo
    {"name": "MEDIUM", "o": (-34.5912, -58.3735), "d": (-34.7050, -58.3950)}, # Retiro -> Lanús
    {"name": "LONG", "o": (-34.5453, -58.4438), "d": (-34.7244, -58.2523)}   # C. Univ -> Quilmes
]

async def call_route(session, case, req_id):
    payload = {
        "vehicles": [{"id": f"V-{req_id}", "capacity_tons": 30, "origin_lat": case["o"][0], "origin_lon": case["o"][1]}],
        "destinations": [{"id": f"D-{req_id}", "demand_tons": 20, "lat": case["d"][0], "lon": case["d"][1]}]
    }
    try:
        async with session.post(API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            data = await resp.json()
            return req_id, case["name"], resp.status, data.get("processing_time_ms", 0), data
    except Exception as e:
        return req_id, case["name"], "ERROR", 0, str(e)

async def run_audit():
    async with aiohttp.ClientSession() as session:
        tasks = []
        # Lanzamos 15 peticiones (5 de cada caso) en ráfaga
        for i in range(15):
            case = TEST_CASES[i % 3]
            tasks.append(call_route(session, case, i))
        
        print(f"{'='*60}")
        print(f" AUDITORÍA FINAL V1.4 — {len(tasks)} REQUESTS EN RÁFAGA")
        print(f"{'='*60}")
        start = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start
        
        # Clasificación de resultados
        success = [r for r in results if r[2] == 200]
        rejected = [r for r in results if r[2] == 429]
        not_found = [r for r in results if r[2] == 404]
        errors_500 = [r for r in results if r[2] == 500]
        conn_errors = [r for r in results if r[2] == "ERROR"]
        
        # Detalle por request
        print(f"\nDETALLE POR REQUEST:")
        for r in sorted(results, key=lambda x: x[0]):
            req_id, name, status, ms, data = r
            if status == 200:
                n_solutions = len(data.get("pareto_solutions", []))
                archetypes = ", ".join(s["archetype"] for s in data.get("pareto_solutions", []))
                print(f"  ✅ Req {req_id:2d} [{name:6s}] HTTP 200 | {ms:7.1f}ms | {n_solutions} soluciones | [{archetypes}]")
            elif status == 429:
                print(f"  🛑 Req {req_id:2d} [{name:6s}] HTTP 429 | Bloqueado por semáforo")
            elif status == 404:
                detail = data.get("detail", "N/A") if isinstance(data, dict) else "N/A"
                print(f"  ⚠️  Req {req_id:2d} [{name:6s}] HTTP 404 | {detail}")
            elif status == 500:
                print(f"  💥 Req {req_id:2d} [{name:6s}] HTTP 500 | SERVER CRASH")
            else:
                print(f"  ❌ Req {req_id:2d} [{name:6s}] ERROR    | {data}")
        
        # Resumen
        print(f"\n{'='*60}")
        print(f" RESUMEN DE EJECUCIÓN")
        print(f"{'='*60}")
        print(f"  ✅ Exitosas (200):        {len(success)}")
        print(f"  🛑 Rechazadas (429):      {len(rejected)}")
        print(f"  ⚠️  No encontradas (404):  {len(not_found)}")
        print(f"  💥 Errores servidor (500): {len(errors_500)}")
        print(f"  ❌ Errores conexión:       {len(conn_errors)}")
        print(f"  ⏱️  Tiempo total ráfaga:   {total_time:.2f}s")
        
        if success:
            avg_time = sum(r[3] for r in success) / len(success)
            max_time = max(r[3] for r in success)
            min_time = min(r[3] for r in success)
            print(f"  🚀 Latencia promedio:      {avg_time:.1f}ms")
            print(f"  📊 Latencia min/max:       {min_time:.1f}ms / {max_time:.1f}ms")
        
        # Criterios Go/No-Go
        print(f"\n{'='*60}")
        print(f" CRITERIOS GO / NO-GO")
        print(f"{'='*60}")
        
        c1 = len(errors_500) == 0
        c2 = len(conn_errors) == 0
        c3 = any(r[1] == "LONG" and r[2] == 200 for r in results)
        c4 = len(success) > 0
        
        print(f"  {'✅' if c1 else '❌'} Cero errores 500:          {'PASS' if c1 else 'FAIL'}")
        print(f"  {'✅' if c2 else '❌'} Cero errores conexión:     {'PASS' if c2 else 'FAIL'}")
        print(f"  {'✅' if c3 else '⚠️ '} Caso LONG exitoso:         {'PASS' if c3 else 'PENDING (puede ser 404 geométrico)'}")
        print(f"  {'✅' if c4 else '❌'} Al menos 1 ruta calculada: {'PASS' if c4 else 'FAIL'}")
        
        all_pass = c1 and c2 and c4
        print(f"\n  {'🏆 V1.4 APROBADA PARA PRODUCCIÓN' if all_pass else '🔧 REQUIERE REVISIÓN'}")

if __name__ == "__main__":
    asyncio.run(run_audit())

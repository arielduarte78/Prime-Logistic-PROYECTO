#!/usr/bin/env python3
"""
torture_test.py — Prime Logistics Engine PRR Chaos Suite
Levanta Uvicorn, ejecuta tres fases de ataque y lo apaga solo.
Uso: python scripts/torture_test.py
"""
import asyncio
import subprocess
import sys
import time
import os
import signal
from pathlib import Path

import httpx
import psutil

# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("PRIME_API_KEY", "dev_key_123")
HEADERS = {"X-API-Key": API_KEY}
PROJECT_ROOT = Path(__file__).resolve().parent.parent

VALID_ROUTE = {
    "vehicles": [{"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 10}],
    "destinations": [{"id": "d1", "lat": -34.5200, "lon": -58.4500, "demand_tons": 2}]
}
VALID_FLEET = {
    "vehicles": [
        {"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 10},
        {"id": "v2", "origin_lat": -34.6100, "origin_lon": -58.3900, "capacity_tons": 8}
    ],
    "destinations": [
        {"id": "d1", "lat": -34.5200, "lon": -58.4500, "demand_tons": 2},
        {"id": "d2", "lat": -34.6500, "lon": -58.5000, "demand_tons": 3}
    ],
    "allowed_archetypes": ["equilibrista"],
    "time_limit_seconds": 5
}

POISON_ROUTE_PAYLOADS = [
    # Océano Pacífico
    {"vehicles": [{"id": "v1", "origin_lat": -10.0, "origin_lon": -140.0, "capacity_tons": 10}],
     "destinations": [{"id": "d1", "lat": -11.0, "lon": -141.0, "demand_tons": 1}]},
    # Origen == Destino
    {"vehicles": [{"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 10}],
     "destinations": [{"id": "d1", "lat": -34.6037, "lon": -58.3816, "demand_tons": 1}]},
    # departure_time inválido
    {"vehicles": [{"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 10}],
     "destinations": [{"id": "d1", "lat": -34.52, "lon": -58.45, "demand_tons": 1}],
     "departure_time": "hora_pico"},
    {"vehicles": [{"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 10}],
     "destinations": [{"id": "d1", "lat": -34.52, "lon": -58.45, "demand_tons": 1}],
     "departure_time": "25:99"},
    # Sin vehicles
    {"vehicles": [], "destinations": [{"id": "d1", "lat": -34.52, "lon": -58.45, "demand_tons": 1}]},
    # Sin destinations
    {"vehicles": [{"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 10}],
     "destinations": []},
]

POISON_FLEET_PAYLOADS = [
    # Demanda negativa
    {"vehicles": [{"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 0}],
     "destinations": [{"id": "d1", "lat": -34.52, "lon": -58.45, "demand_tons": -5}],
     "allowed_archetypes": ["equilibrista"], "time_limit_seconds": 5},
    # Capacidad cero
    {"vehicles": [{"id": "v1", "origin_lat": -34.6037, "origin_lon": -58.3816, "capacity_tons": 0}],
     "destinations": [{"id": "d1", "lat": -34.52, "lon": -58.45, "demand_tons": 1}],
     "allowed_archetypes": ["equilibrista"], "time_limit_seconds": 5},
]

# ---------------------------------------------------------------------------
# UTILS
# ---------------------------------------------------------------------------

def print_banner(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def get_uvicorn_ram_mb() -> float:
    for proc in psutil.process_iter(['name', 'cmdline', 'memory_info']):
        try:
            if 'uvicorn' in ' '.join(proc.info['cmdline'] or []):
                return proc.info['memory_info'].rss / 1024 / 1024
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return 0.0

async def wait_for_server(timeout: int = 60) -> bool:
    print("⏳ Esperando que Uvicorn esté listo...")
    async with httpx.AsyncClient() as client:
        for _ in range(timeout):
            try:
                r = await client.get(f"{BASE_URL}/docs", timeout=2.0)
                if r.status_code < 500:
                    print("✓ Servidor listo.")
                    return True
            except Exception:
                pass
            await asyncio.sleep(1)
    return False

async def measure_latency(client: httpx.AsyncClient) -> float:
    t0 = time.perf_counter()
    try:
        await client.get(f"{BASE_URL}/docs", timeout=5.0)
    except Exception:
        pass
    return (time.perf_counter() - t0) * 1000

# ---------------------------------------------------------------------------
# FASE 1 — FUZZING
# ---------------------------------------------------------------------------

async def fase1_fuzzing(client: httpx.AsyncClient) -> dict:
    print_banner("FASE 1 — Fuzzing Geométrico y Semántico")
    results = {"passed": 0, "failed_500": 0, "details": []}

    async def fire(endpoint, payload, label):
        try:
            r = await client.post(f"{BASE_URL}/{endpoint}", json=payload,
                                  headers=HEADERS, timeout=30.0)
            status = r.status_code
            ok = status in (400, 404, 422, 429)
            symbol = "✓" if ok else "✗ FAIL"
            print(f"  [{symbol}] {label} → HTTP {status}")
            if not ok:
                results["failed_500"] += 1
                results["details"].append(f"{label}: HTTP {status}")
            else:
                results["passed"] += 1
        except Exception as e:
            print(f"  [✗ CRASH] {label} → {e}")
            results["failed_500"] += 1
            results["details"].append(f"{label}: CRASH {e}")

    for i, p in enumerate(POISON_ROUTE_PAYLOADS):
        await fire("route", p, f"route/poison-{i+1}")
    for i, p in enumerate(POISON_FLEET_PAYLOADS):
        await fire("fleet", p, f"fleet/poison-{i+1}")

    print(f"\n  Resultado Fase 1: {results['passed']} OK | {results['failed_500']} FALLOS CRÍTICOS")
    return results

# ---------------------------------------------------------------------------
# FASE 2 — CONCURRENCY BOMB
# ---------------------------------------------------------------------------

async def fase2_concurrency(client: httpx.AsyncClient) -> dict:
    print_banner("FASE 2 — Concurrency Bomb (50 route + 10 fleet simultáneos)")
    results = {"http_429": 0, "http_200": 0, "http_500": 0, "other": 0}

    async def fire_route(_):
        try:
            r = await client.post(f"{BASE_URL}/route", json=VALID_ROUTE,
                                  headers=HEADERS, timeout=60.0)
            return r.status_code
        except Exception:
            return 0

    async def fire_fleet(_):
        try:
            r = await client.post(f"{BASE_URL}/fleet", json=VALID_FLEET,
                                  headers=HEADERS, timeout=120.0)
            return r.status_code
        except Exception:
            return 0

    tasks = [fire_route(i) for i in range(50)] + [fire_fleet(i) for i in range(10)]
    statuses = await asyncio.gather(*tasks)

    for s in statuses:
        if s == 429:
            results["http_429"] += 1
        elif s == 200:
            results["http_200"] += 1
        elif s == 500:
            results["http_500"] += 1
        else:
            results["other"] += 1

    print(f"  HTTP 200 (procesados): {results['http_200']}")
    print(f"  HTTP 429 (rechazados limpiamente): {results['http_429']}")
    print(f"  HTTP 500 (errores críticos): {results['http_500']}")
    print(f"  Otros: {results['other']}")

    if results["http_500"] == 0:
        print("  ✓ Sin errores 500 bajo carga máxima.")
    else:
        print(f"  ✗ CRÍTICO: {results['http_500']} errores 500 detectados.")

    return results

# ---------------------------------------------------------------------------
# FASE 3 — MEMORY LEAK PROFILER
# ---------------------------------------------------------------------------

async def fase3_memory(client: httpx.AsyncClient) -> dict:
    print_banner("FASE 3 — Memory Leak Profiler")

    ram_before = get_uvicorn_ram_mb()
    latency_before = await measure_latency(client)
    print(f"  RAM antes del ataque  : {ram_before:.1f} MB")
    print(f"  Latencia antes        : {latency_before:.1f} ms")

    # Mini-bombardeo de 20 requests para estresar memoria
    tasks = [client.post(f"{BASE_URL}/route", json=VALID_ROUTE,
                         headers=HEADERS, timeout=60.0) for _ in range(20)]
    await asyncio.gather(*tasks, return_exceptions=True)

    latency_during = await measure_latency(client)
    ram_during = get_uvicorn_ram_mb()
    print(f"  RAM durante ataque    : {ram_during:.1f} MB")
    print(f"  Latencia durante      : {latency_during:.1f} ms")

    print("  ⏳ Esperando 5s para gc.collect()...")
    await asyncio.sleep(5)

    ram_after = get_uvicorn_ram_mb()
    latency_after = await measure_latency(client)
    print(f"  RAM después (5s)      : {ram_after:.1f} MB")
    print(f"  Latencia después      : {latency_after:.1f} ms")

    delta = ram_after - ram_before
    leak_detected = delta > 50
    if leak_detected:
        print(f"  ✗ POSIBLE LEAK: +{delta:.1f} MB retenidos después del GC.")
    else:
        print(f"  ✓ Memoria estable. Delta: {delta:+.1f} MB")

    return {"ram_before": ram_before, "ram_after": ram_after,
            "delta_mb": delta, "leak_detected": leak_detected}

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

async def main():
    print_banner("PRIME LOGISTICS — PRR Chaos & Fuzzing Suite")

    # Levantar Uvicorn automáticamente
    print("\n🚀 Levantando Uvicorn...")
    uvicorn_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app",
         "--host", "0.0.0.0", "--port", "8000", "--workers", "1"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid if sys.platform != "win32" else None
    )

    try:
        ready = await wait_for_server(timeout=120)
        if not ready:
            print("✗ El servidor no respondió en 120s. Abortando.")
            uvicorn_proc.terminate()
            sys.exit(1)

        async with httpx.AsyncClient() as client:
            r1 = await fase1_fuzzing(client)
            r2 = await fase2_concurrency(client)
            r3 = await fase3_memory(client)

        # Reporte final
        print_banner("REPORTE FINAL PRR")
        total_500 = r1["failed_500"] + r2["http_500"]
        print(f"  Fase 1 — Fuzzing       : {r1['passed']} OK | {r1['failed_500']} CRÍTICOS")
        print(f"  Fase 2 — Concurrencia  : {r2['http_200']} procesados | {r2['http_429']} rechazados | {r2['http_500']} errores")
        print(f"  Fase 3 — Memoria       : delta {r3['delta_mb']:+.1f} MB | leak={'SÍ ✗' if r3['leak_detected'] else 'NO ✓'}")
        print(f"\n  TOTAL HTTP 500 : {total_500}")

        if total_500 == 0 and not r3["leak_detected"]:
            print("\n  ✅ CERTIFICADO PARA PRODUCCIÓN")
        else:
            print("\n  ❌ REQUIERE ATENCIÓN ANTES DE PRODUCCIÓN")

    finally:
        print("\n🛑 Apagando Uvicorn...")
        if sys.platform != "win32":
            os.killpg(os.getpgid(uvicorn_proc.pid), signal.SIGTERM)
        else:
            uvicorn_proc.terminate()
        uvicorn_proc.wait()
        print("✓ Servidor apagado.")

if __name__ == "__main__":
    asyncio.run(main())

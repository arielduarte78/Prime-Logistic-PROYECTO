import asyncio
import httpx
import pytest

import main
from src.api.schemas import FleetResponse

BODY = {
    "vehicles": [{"id": "t", "origin_lat": -34.60, "origin_lon": -58.38, "capacity_tons": 10.0}],
    "destinations": [{"id": "d", "lat": -34.62, "lon": -58.39, "demand_tons": 1.0}],
}


async def _calculo_lento(payload, request):
    await asyncio.sleep(0.3)  # simula un /fleet que tarda
    return FleetResponse(subgraph_edges=0, total_time_ms=300.0, phase4_total_legs=0, plans={})


def _dos_fleet_a_la_vez():
    async def caso():
        transporte = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://test") as c:
            h = {"x-api-key": "test_key_123"}
            return await asyncio.gather(c.post("/fleet", json=BODY, headers=h),
                                        c.post("/fleet", json=BODY, headers=h))
    return asyncio.run(caso())


def test_dos_fleet_simultaneos_el_segundo_espera_y_responde_200(mock_app_state, monkeypatch):
    """Antes el segundo rebotaba al instante con 429 ('El motor está procesando otra solicitud')."""
    from src.api.cola import Cola
    monkeypatch.setattr(main, "calculate_fleet", _calculo_lento)
    mock_app_state.cola_fleet = Cola(en_paralelo=1, max_en_espera=3, espera_max_s=5)
    mock_app_state.fleet_semaphore = asyncio.Semaphore(1)  # por si corre contra el código viejo
    r1, r2 = _dos_fleet_a_la_vez()
    assert (r1.status_code, r2.status_code) == (200, 200), (r1.text, r2.text)


def test_cola_llena_responde_429_claro_con_retry_after(mock_app_state, monkeypatch):
    from src.api.cola import Cola
    monkeypatch.setattr(main, "calculate_fleet", _calculo_lento)
    mock_app_state.cola_fleet = Cola(en_paralelo=1, max_en_espera=0, espera_max_s=5)
    r1, r2 = _dos_fleet_a_la_vez()
    codigos = sorted([r1.status_code, r2.status_code])
    assert codigos == [200, 429]
    rebote = r1 if r1.status_code == 429 else r2
    assert rebote.headers.get("retry-after") == "30"
    assert "ocupado" in rebote.json()["detail"].lower()


def test_cors_deja_leer_retry_after_al_frontend(test_client):
    """Sin Access-Control-Expose-Headers el navegador no puede leer Retry-After desde Vercel."""
    r = test_client.post("/fleet", json=BODY, headers={
        "x-api-key": "clave-mala", "Origin": "https://abbey-frontend-rho.vercel.app"})
    expuestos = r.headers.get("access-control-expose-headers", "").lower()
    assert "retry-after" in expuestos

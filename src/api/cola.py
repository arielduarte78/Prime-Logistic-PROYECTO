# src/api/cola.py
"""
Cola de espera para los endpoints pesados (/fleet y /route).

Antes: si el motor estaba ocupado, la solicitud esperaba 0,1 s y rebotaba con 429.
Ahora: la solicitud espera su turno hasta `espera_max_s` segundos. Solo rebota si
  - ya hay `max_en_espera` solicitudes esperando (para no acumular gente sin fin), o
  - pasó el tiempo máximo de espera.
En los dos casos responde 429 con un mensaje claro y el header Retry-After.

El turno se libera SIEMPRE (con `finally`), aunque el cálculo falle o el cliente se vaya.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import HTTPException

REINTENTAR_EN_S = 30  # lo que le sugerimos al cliente cuando rebota


class Cola:
    def __init__(self, en_paralelo: int, max_en_espera: int, espera_max_s: float):
        self._semaforo = asyncio.Semaphore(en_paralelo)
        self.max_en_espera = max_en_espera
        self.espera_max_s = espera_max_s
        self.esperando = 0  # solicitudes que esperan turno
        self.ocupados = 0   # solicitudes que se están calculando

    def _rebote(self, motivo: str) -> HTTPException:
        return HTTPException(
            status_code=429,
            detail=f"El motor está ocupado: {motivo}. Probá de nuevo en {REINTENTAR_EN_S} segundos.",
            headers={"Retry-After": str(REINTENTAR_EN_S)},
        )

    @asynccontextmanager
    async def turno(self):
        if self._semaforo.locked() and self.esperando >= self.max_en_espera:
            raise self._rebote(f"ya hay {self.esperando} solicitudes en espera")

        self.esperando += 1
        try:
            await asyncio.wait_for(self._semaforo.acquire(), timeout=self.espera_max_s)
        except asyncio.TimeoutError:
            raise self._rebote(f"esperaste más de {int(self.espera_max_s)} segundos")
        finally:
            self.esperando -= 1

        self.ocupados += 1
        try:
            yield
        finally:
            self.ocupados -= 1
            self._semaforo.release()

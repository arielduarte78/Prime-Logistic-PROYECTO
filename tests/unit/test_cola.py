"""
La cola de /fleet y /route: en vez de rebotar al instante con 429 (antes esperaba 0,1 s),
una solicitud espera su turno un tiempo razonable. El turno SIEMPRE se libera.
"""
import asyncio
import pytest
from fastapi import HTTPException
from src.api.cola import Cola


def correr(coro):
    return asyncio.run(coro)


def test_la_segunda_solicitud_espera_su_turno_en_vez_de_rebotar():
    async def caso():
        cola = Cola(en_paralelo=1, max_en_espera=3, espera_max_s=5)
        orden = []

        async def trabajo(nombre, dura):
            async with cola.turno():
                orden.append(f"empieza {nombre}")
                await asyncio.sleep(dura)
                orden.append(f"termina {nombre}")

        await asyncio.gather(trabajo("A", 0.3), trabajo("B", 0.01))
        return orden

    assert correr(caso()) == ["empieza A", "termina A", "empieza B", "termina B"]


def test_si_espera_demasiado_responde_429_con_retry_after():
    async def caso():
        cola = Cola(en_paralelo=1, max_en_espera=3, espera_max_s=0.2)

        async def largo():
            async with cola.turno():
                await asyncio.sleep(1)

        tarea = asyncio.create_task(largo())
        await asyncio.sleep(0.05)
        with pytest.raises(HTTPException) as exc:
            async with cola.turno():
                pass
        tarea.cancel()
        return exc.value

    e = correr(caso())
    assert e.status_code == 429
    assert "Retry-After" in e.headers
    assert "ocupado" in e.detail.lower()


def test_con_la_cola_llena_rebota_al_instante():
    async def caso():
        cola = Cola(en_paralelo=1, max_en_espera=1, espera_max_s=5)

        async def largo():
            async with cola.turno():
                await asyncio.sleep(1)

        t1 = asyncio.create_task(largo())          # trabajando
        await asyncio.sleep(0.05)
        t2 = asyncio.create_task(largo())          # esperando (la cola se llenó)
        await asyncio.sleep(0.05)
        inicio = asyncio.get_running_loop().time()
        with pytest.raises(HTTPException) as exc:
            async with cola.turno():
                pass
        demora = asyncio.get_running_loop().time() - inicio
        t1.cancel(); t2.cancel()
        return exc.value, demora

    e, demora = correr(caso())
    assert e.status_code == 429 and demora < 0.1


def test_el_turno_se_libera_aunque_el_calculo_explote():
    async def caso():
        cola = Cola(en_paralelo=1, max_en_espera=3, espera_max_s=0.5)
        with pytest.raises(ValueError):
            async with cola.turno():
                raise ValueError("falló el cálculo")
        async with cola.turno():   # si no se hubiera liberado, esto daría 429
            return cola.ocupados, cola.esperando

    assert correr(caso()) == (1, 0)


def test_el_turno_se_libera_si_cancelan_la_espera():
    async def caso():
        cola = Cola(en_paralelo=1, max_en_espera=3, espera_max_s=5)

        async def largo():
            async with cola.turno():
                await asyncio.sleep(0.3)

        t1 = asyncio.create_task(largo())
        await asyncio.sleep(0.05)
        t2 = asyncio.create_task(largo())
        await asyncio.sleep(0.05)
        t2.cancel()                                # el cliente se fue mientras esperaba
        await asyncio.gather(t1, t2, return_exceptions=True)
        return cola.ocupados, cola.esperando

    assert correr(caso()) == (0, 0)

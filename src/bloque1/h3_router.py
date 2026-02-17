"""Corredor H3 para Prime Logistics v1.2."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Set, Tuple
import logging
import time

logger = logging.getLogger(__name__)

def assert_h3_api() -> None:
    """Valida la API en runtime/bootstrap para permitir mocking en tests."""
    import h3
    REQUIRED_H3_FUNCS = ["latlng_to_cell", "grid_path_cells", "grid_disk"]
    for fn in REQUIRED_H3_FUNCS:
        if not hasattr(h3, fn):
            raise RuntimeError(f"Falta la función '{fn}'. Pinnea h3>=4.0.0")

@dataclass(frozen=True)
class RouteEndpoint:
    name: str
    lat: float
    lon: float

@dataclass(frozen=True)
class H3Corridor:
    origin_cell: str
    destination_cell: str
    direct_path_cells: Tuple[str, ...]
    buffered_cells: Tuple[str, ...]
    # Telemetría y Observabilidad
    truncated: bool = False
    num_direct_cells: int = 0
    num_buffered_before_trunc: int = 0
    elapsed_ms: float = 0.0

def _validate_coords(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"Coordenadas fuera de rango: Lat {lat}, Lon {lon}")

def build_h3_corridor(origin: RouteEndpoint, destination: RouteEndpoint, 
                      resolution: int, buffer_rings: int = 1, 
                      max_cells: int = 20000) -> H3Corridor:
    """Calcula corredor H3 midiendo latencia y previniendo desbordamientos."""
    assert_h3_api()
    start_time = time.perf_counter()
    import h3
    
    _validate_coords(origin.lat, origin.lon)
    _validate_coords(destination.lat, destination.lon)

    origin_cell = h3.latlng_to_cell(origin.lat, origin.lon, resolution)
    destination_cell = h3.latlng_to_cell(destination.lat, destination.lon, resolution)

    if origin_cell == destination_cell:
        direct_path = (origin_cell,)
    else:
        try:
            direct_path = tuple(h3.grid_path_cells(origin_cell, destination_cell))
        except Exception:
            # Contexto agregado al log
            logger.exception("h3.grid_path_cells falló. Contexto: origin=%s, dest=%s, res=%s", 
                             origin.name, destination.name, resolution)
            direct_path = (origin_cell, destination_cell)

    buffered: Set[str] = set(direct_path)
    is_truncated = False

    if buffer_rings > 0:
        for cell in direct_path:
            neighbors = h3.grid_disk(cell, buffer_rings)
            buffered.update(neighbors)
            if len(buffered) > max_cells:
                logger.error("Buffer excedió max_cells=%s en %s->%s. Truncando...", 
                             max_cells, origin.name, destination.name)
                is_truncated = True
                break
    
    num_before_trunc = len(buffered)
    if is_truncated:
        # Truncado determinista: ordenar antes de cortar
        buffered = set(sorted(buffered)[:max_cells])

    elapsed = (time.perf_counter() - start_time) * 1000.0

    if is_truncated:
        logger.info("Evento Truncado: origin=%s, dest=%s, celdas_finales=%s", 
                    origin.name, destination.name, len(buffered))

    return H3Corridor(
        origin_cell=origin_cell,
        destination_cell=destination_cell,
        direct_path_cells=direct_path,
        buffered_cells=tuple(sorted(buffered)),
        truncated=is_truncated,
        num_direct_cells=len(direct_path),
        num_buffered_before_trunc=num_before_trunc,
        elapsed_ms=elapsed
    )

def split_cells(cells: Iterable[str], origin_cell: str, destination_cell: str, local_rings: int = 1):
    assert_h3_api()
    import h3
    cells_set = set(cells)
    origin_local_zone = set(h3.grid_disk(origin_cell, local_rings))
    dest_local_zone = set(h3.grid_disk(destination_cell, local_rings))

    origin_cells = tuple(sorted(c for c in cells_set if c in origin_local_zone))
    destination_cells = tuple(sorted(c for c in cells_set if c in dest_local_zone))
    trunk_cells = tuple(sorted(c for c in cells_set if c not in origin_local_zone and c not in dest_local_zone))

    return origin_cells, destination_cells, trunk_cells

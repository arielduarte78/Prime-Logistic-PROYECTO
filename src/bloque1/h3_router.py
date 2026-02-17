"""Corredor H3 para Prime Logistics v1.2 - Versión auditada y corregida."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Set, Tuple, Optional, Callable, Any, Dict
import logging
import time
import math
import threading
import os

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Configuración por entorno (sobrescribible con variables de entorno)
# ----------------------------------------------------------------------
_MAX_BUFFER_RINGS = int(os.environ.get("H3_MAX_BUFFER_RINGS", "10"))
_MAX_ALLOWED_CELLS = int(os.environ.get("H3_MAX_ALLOWED_CELLS", "200000"))

# ----------------------------------------------------------------------
# Adaptador H3 multi‑versión (thread‑safe, wrappers normalizados)
# ----------------------------------------------------------------------

_H3_ADAPTER: Optional[Dict[str, Any]] = None
_LOCK = threading.Lock()

def _import_h3_adapter() -> Dict[str, Any]:
    """Detecta la versión de h3 y devuelve un diccionario con funciones normalizadas.
    
    Returns:
        Diccionario con las claves:
        - to_cell: (lat, lon, res) -> str
        - line: (cell_a, cell_b) -> tuple[str, ...] (puede ser None si no existe)
        - disk: (cell, k) -> set[str]
        - to_latlng: (cell) -> (lat: float, lon: float)
        - is_valid_cell: (cell) -> bool
        - version: str versión detectada
    """
    global _H3_ADAPTER
    if _H3_ADAPTER is not None:
        return _H3_ADAPTER

    with _LOCK:
        if _H3_ADAPTER is not None:
            return _H3_ADAPTER

        try:
            import h3
        except ImportError as e:
            raise ImportError(
                "Librería 'h3' no instalada. Ejecuta: pip install h3>=4.0.0  (o conda install -c conda-forge h3)"
            ) from e

        version = getattr(h3, "__version__", "desconocida")
        logger.info("Detectada h3 versión %s", version)

        # ---- to_cell ----
        if hasattr(h3, "latlng_to_cell"):
            _to_cell = h3.latlng_to_cell
        elif hasattr(h3, "geo_to_h3"):
            _to_cell = h3.geo_to_h3
        elif hasattr(h3, "latlng_to_h3"):
            _to_cell = h3.latlng_to_h3
        else:
            raise RuntimeError("No se encontró función de conversión lat/lon a celda H3")

        def to_cell(lat: float, lon: float, res: int) -> str:
            return _to_cell(lat, lon, res)

        # ---- line ----
        if hasattr(h3, "grid_path_cells"):
            _line = h3.grid_path_cells
        elif hasattr(h3, "h3_line"):
            _line = h3.h3_line
        else:
            _line = None

        def line(cell_a: str, cell_b: str) -> Tuple[str, ...]:
            if _line is None:
                raise RuntimeError("Función de línea H3 no disponible")
            return tuple(_line(cell_a, cell_b))

        # ---- disk ----
        if hasattr(h3, "grid_disk"):
            _disk = h3.grid_disk
        elif hasattr(h3, "k_ring"):
            _disk = h3.k_ring
        else:
            raise RuntimeError("No se encontró función de anillo H3")

        def disk(cell: str, k: int) -> Set[str]:
            return set(_disk(cell, k))

        # ---- to_latlng ----
        if hasattr(h3, "cell_to_latlng"):
            _to_latlng = h3.cell_to_latlng
        elif hasattr(h3, "h3_to_geo"):
            _to_latlng = h3.h3_to_geo
        else:
            raise RuntimeError("No se encontró función para obtener centroide de celda")

        def to_latlng(cell: str) -> Tuple[float, float]:
            v = _to_latlng(cell)
            return float(v[0]), float(v[1])

        # ---- is_valid_cell ----
        def is_valid_cell(cell: str) -> bool:
            try:
                if hasattr(h3, "get_resolution"):
                    h3.get_resolution(cell)
                elif hasattr(h3, "h3_get_resolution"):
                    h3.h3_get_resolution(cell)
                else:
                    return isinstance(cell, str) and len(cell) > 0
                return True
            except Exception:
                return False

        _H3_ADAPTER = {
            "to_cell": to_cell,
            "line": line if _line is not None else None,  # exponer None si no existe
            "disk": disk,
            "to_latlng": to_latlng,
            "is_valid_cell": is_valid_cell,
            "version": version,
        }
        return _H3_ADAPTER


# ----------------------------------------------------------------------
# Utilidades geométricas (rápidas)
# ----------------------------------------------------------------------

_EARTH_RADIUS_KM = 6371.0

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en kilómetros entre dos puntos (fórmula de haversine)."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return _EARTH_RADIUS_KM * c

def _distance_to_line(lat: float, lon: float,
                      lat1: float, lon1: float,
                      lat2: float, lon2: float) -> float:
    """
    Distancia aproximada de un punto al segmento (origen-destino).
    Se usa proyección en plano con corrección por coseno de latitud media.
    """
    lat_mean = math.radians((lat1 + lat2) / 2)
    cos_lat = math.cos(lat_mean)

    x = lon * cos_lat
    y = lat
    x1 = lon1 * cos_lat
    y1 = lat1
    x2 = lon2 * cos_lat
    y2 = lat2

    dx = x2 - x1
    dy = y2 - y1

    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)

    t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
    if t < 0:
        return math.hypot(x - x1, y - y1)
    elif t > 1:
        return math.hypot(x - x2, y - y2)
    else:
        projx = x1 + t * dx
        projy = y1 + t * dy
        return math.hypot(x - projx, y - projy)


# ----------------------------------------------------------------------
# Función auxiliar para reintentos con callback de intento
# ----------------------------------------------------------------------

def _call_with_retry(func: Callable, *args,
                     max_attempts: int = 3,
                     base_delay: float = 0.1,
                     attempt_callback: Optional[Callable[[], None]] = None) -> Any:
    """Ejecuta func con reintentos y backoff exponencial, llamando a attempt_callback en cada intento."""
    for attempt in range(1, max_attempts + 1):
        if attempt_callback is not None:
            attempt_callback()
        try:
            return func(*args)
        except Exception:
            if attempt == max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.debug("Reintento %d para %s tras %s s", attempt, getattr(func, "__name__", repr(func)), delay)
            time.sleep(delay)
    return None  # never reached


# ----------------------------------------------------------------------
# Modelos
# ----------------------------------------------------------------------

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
    truncated: bool = False
    num_direct_cells: int = 0
    num_buffered_before_trunc: int = 0
    elapsed_ms: float = 0.0
    error_code: Optional[str] = None          # 'LINE_FAILED', 'LINE_FUNCTION_MISSING', 'DISK_FAILED', 'TRUNCATED', etc.
    adapter_version: str = "desconocida"
    num_disk_calls: int = 0                    # total de intentos (incluye reintentos)
    path_method: str = "h3_line"               # 'h3_line', 'fallback_endpoints', 'same_cell', 'function_missing'


# ----------------------------------------------------------------------
# Validaciones y utilidades de logging
# ----------------------------------------------------------------------

def _validate_coords(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitud fuera de rango: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitud fuera de rango: {lon}")

def _validate_resolution(resolution: int) -> None:
    if not (0 <= resolution <= 15):
        raise ValueError(f"Resolución H3 debe estar entre 0 y 15, recibido {resolution}")

def _safe_name(name: str, max_len: int = 50) -> str:
    """Trunca un nombre para logs si es demasiado largo."""
    if len(name) <= max_len:
        return name
    return name[:max_len-3] + "..."


# ----------------------------------------------------------------------
# Función principal
# ----------------------------------------------------------------------

def build_h3_corridor(origin: RouteEndpoint,
                      destination: RouteEndpoint,
                      resolution: int,
                      buffer_rings: int = 1,
                      max_cells: int = 20000) -> H3Corridor:
    """
    Construye un corredor de celdas H3 entre origen y destino.
    
    Si truncated==True, buffered_cells se ordena por proximidad geográfica al segmento.
    Si truncated==False, buffered_cells se ordena alfabéticamente para determinismo.
    """
    # Validaciones
    _validate_coords(origin.lat, origin.lon)
    _validate_coords(destination.lat, destination.lon)
    _validate_resolution(resolution)
    if buffer_rings < 0:
        raise ValueError(f"buffer_rings debe ser >= 0, recibido {buffer_rings}")
    if buffer_rings > _MAX_BUFFER_RINGS:
        raise ValueError(f"buffer_rings excede el máximo permitido {_MAX_BUFFER_RINGS}")
    if max_cells <= 0:
        raise ValueError(f"max_cells debe ser > 0, recibido {max_cells}")
    if max_cells > _MAX_ALLOWED_CELLS:
        raise ValueError(f"max_cells demasiado alto ({max_cells}), máximo permitido {_MAX_ALLOWED_CELLS}")

    adapter = _import_h3_adapter()
    to_cell = adapter["to_cell"]
    line_func = adapter["line"]          # puede ser None
    disk_func = adapter["disk"]
    to_latlng = adapter["to_latlng"]
    is_valid_cell = adapter["is_valid_cell"]
    adapter_version = adapter["version"]

    start_time = time.perf_counter()
    error_code = None
    path_method = "h3_line"
    disk_attempts = 0

    # Celdas de origen y destino
    origin_cell = to_cell(origin.lat, origin.lon, resolution)
    destination_cell = to_cell(destination.lat, destination.lon, resolution)

    if not (is_valid_cell(origin_cell) and is_valid_cell(destination_cell)):
        raise ValueError("No se pudieron generar celdas H3 válidas para origen/destino")

    # Path directo
    if origin_cell == destination_cell:
        direct_path = (origin_cell,)
        path_method = "same_cell"
    else:
        if line_func is None:
            # La función de línea no existe en esta versión de h3
            logger.warning(
                "Función de línea H3 no disponible en adaptador %s para %s->%s. Usando extremos.",
                adapter_version, _safe_name(origin.name), _safe_name(destination.name)
            )
            direct_path = (origin_cell, destination_cell)
            path_method = "function_missing"
            error_code = "LINE_FUNCTION_MISSING"
        else:
            try:
                direct_path = _call_with_retry(line_func, origin_cell, destination_cell,
                                               max_attempts=3, base_delay=0.1)
                path_method = "h3_line"
            except Exception:
                logger.exception(
                    "Fallo en h3_line después de reintentos para %s->%s (res=%s, buffer=%s, max_cells=%s, adapter=%s). Usando extremos.",
                    _safe_name(origin.name), _safe_name(destination.name), resolution, buffer_rings, max_cells, adapter_version
                )
                direct_path = (origin_cell, destination_cell)
                path_method = "fallback_endpoints"
                error_code = "LINE_FAILED"

    # Construir buffer
    buffered_set: Set[str] = set(direct_path)
    truncated = False
    num_before_trunc = 0

    if buffer_rings > 0:
        for cell in direct_path:
            def count_attempt():
                nonlocal disk_attempts
                disk_attempts += 1

            try:
                neighbors = _call_with_retry(disk_func, cell, buffer_rings,
                                             max_attempts=3, base_delay=0.1,
                                             attempt_callback=count_attempt)
                buffered_set.update(neighbors)
                if len(buffered_set) > max_cells:
                    logger.warning(
                        "Buffer excedió max_cells=%s en %s->%s (res=%s, buffer=%s, adapter=%s, disk_attempts=%d). Truncando por proximidad geográfica.",
                        max_cells, _safe_name(origin.name), _safe_name(destination.name), resolution, buffer_rings, adapter_version, disk_attempts
                    )
                    truncated = True
                    error_code = "TRUNCATED"
                    break
            except Exception:
                logger.exception(
                    "Fallo en grid_disk para celda %s en %s->%s (res=%s, buffer=%s, adapter=%s, disk_attempts=%d). Se omite.",
                    cell, _safe_name(origin.name), _safe_name(destination.name), resolution, buffer_rings, adapter_version, disk_attempts
                )
                error_code = "DISK_FAILED"
                # continuamos

        num_before_trunc = len(buffered_set)

    # Truncado por proximidad geográfica
    if truncated:
        # Pre‑filtrado eficiente si el conjunto es muy grande
        if len(buffered_set) > max_cells * 5:
            # Construir candidatos en orden de aparición: direct_path primero, luego vecinos de orden 1
            ordered_cells = []
            for cell in direct_path:
                ordered_cells.append(cell)
            for cell in direct_path:
                try:
                    for n in disk_func(cell, 1):
                        ordered_cells.append(n)
                except Exception:
                    pass
            # Eliminar duplicados preservando orden
            ordered_cells = list(dict.fromkeys(ordered_cells))
            if len(ordered_cells) > max_cells * 5:
                ordered_cells = ordered_cells[:max_cells * 5]
            buffered_to_process = ordered_cells
        else:
            buffered_to_process = list(buffered_set)

        # Calcular distancias al segmento con caché de centroides
        lat1, lon1 = to_latlng(origin_cell)
        lat2, lon2 = to_latlng(destination_cell)
        centroid_cache: dict[str, tuple[float, float]] = {}
        cells_with_dist = []
        for cell in buffered_to_process:
            if cell in centroid_cache:
                clat, clon = centroid_cache[cell]
            else:
                clat, clon = to_latlng(cell)
                centroid_cache[cell] = (clat, clon)
            dist = _distance_to_line(clat, clon, lat1, lon1, lat2, lon2)
            cells_with_dist.append((dist, cell))
        cells_with_dist.sort(key=lambda x: x[0])
        selected_cells = [cell for _, cell in cells_with_dist[:max_cells]]
        buffered_final = selected_cells   # mantiene orden por prioridad geográfica
    else:
        buffered_final = sorted(buffered_set)   # determinismo alfabético

    elapsed = (time.perf_counter() - start_time) * 1000.0

    return H3Corridor(
        origin_cell=origin_cell,
        destination_cell=destination_cell,
        direct_path_cells=direct_path,
        buffered_cells=tuple(buffered_final),
        truncated=truncated,
        num_direct_cells=len(direct_path),
        num_buffered_before_trunc=num_before_trunc,
        elapsed_ms=elapsed,
        error_code=error_code,
        adapter_version=adapter_version,
        num_disk_calls=disk_attempts,
        path_method=path_method,
    )


# ----------------------------------------------------------------------
# División del corredor en zonas (origen, troncal, destino)
# ----------------------------------------------------------------------

def split_cells(cells: Iterable[str],
                origin_cell: str,
                destination_cell: str,
                local_rings: int = 1) -> Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]:
    """
    Divide un conjunto de celdas H3 en tres grupos:
    - origin_cells: celdas cercanas al origen (incluyendo su anillo local_rings)
    - destination_cells: celdas cercanas al destino
    - trunk_cells: el resto
    """
    if local_rings < 0:
        raise ValueError(f"local_rings debe ser >= 0, recibido {local_rings}")

    adapter = _import_h3_adapter()
    is_valid = adapter["is_valid_cell"]
    disk = adapter["disk"]

    if not (is_valid(origin_cell) and is_valid(destination_cell)):
        raise ValueError("origin_cell o destination_cell no son celdas H3 válidas")

    origin_zone = set(disk(origin_cell, local_rings)) if local_rings > 0 else {origin_cell}
    dest_zone = set(disk(destination_cell, local_rings)) if local_rings > 0 else {destination_cell}

    cells_set = set(cells)
    for c in cells_set:
        if not is_valid(c):
            logger.warning("Celda inválida encontrada en split_cells: %s", c)

    origin_cells = tuple(sorted(c for c in cells_set if c in origin_zone))
    destination_cells = tuple(sorted(c for c in cells_set if c in dest_zone))
    trunk_cells = tuple(sorted(c for c in cells_set if c not in origin_zone and c not in dest_zone))

    return origin_cells, destination_cells, trunk_cells


# ----------------------------------------------------------------------
# Exportación pública del módulo
# ----------------------------------------------------------------------
__all__ = ["RouteEndpoint", "build_h3_corridor", "split_cells"]

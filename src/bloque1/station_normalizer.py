# src/bloque1/station_normalizer.py
"""
Normalización Semántica de Tipos de Estación — Prime Logistics v1.3.5.

Implementa un mapeo canónico que traduce strings sucios o sinónimos
(e.g., "deposito", "DC", "cd", "distribution center") al estándar
del sistema (e.g., "warehouse").

Uso:
    from src.bloque1.station_normalizer import normalize_station_type
    canonical = normalize_station_type("deposito")  # -> "warehouse"
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# =====================================================================
# MAPEO CANÓNICO (FUENTE DE VERDAD SEMÁNTICA)
# =====================================================================
# Claves: formas sucias / sinónimos (siempre en lowercase).
# Valores: etiqueta canónica del sistema.
#
# Para agregar un nuevo sinónimo, simplemente añadir una entrada aquí.
# El sistema recalculará automáticamente.
# =====================================================================

CANONICAL_STATION_MAP: dict[str, str] = {
    # --- warehouse / almacén ---
    "warehouse":            "warehouse",
    "almacen":              "warehouse",
    "almacén":              "warehouse",
    "deposito":             "warehouse",
    "depósito":             "warehouse",
    "depot":                "warehouse",
    "dc":                   "warehouse",
    "cd":                   "warehouse",
    "distribution center":  "warehouse",
    "centro de distribucion": "warehouse",
    "centro de distribución": "warehouse",
    "storage":              "warehouse",
    "bodega":               "warehouse",

    # --- factory / fábrica ---
    "factory":              "factory",
    "fabrica":              "factory",
    "fábrica":              "factory",
    "planta":               "factory",
    "plant":                "factory",
    "manufacturing":        "factory",

    # --- terminal ---
    "terminal":             "terminal",
    "hub":                  "terminal",
    "centro logistico":     "terminal",
    "centro logístico":     "terminal",
    "cross_dock":           "terminal",
    "crossdock":            "terminal",
    "cross-dock":           "terminal",

    # --- airport ---
    "airport":              "airport",
    "aeropuerto":           "airport",

    # --- port ---
    "port":                 "port",
    "puerto":               "port",
    "harbor":               "port",
    "harbour":              "port",

    # --- rail_terminal ---
    "rail_terminal":        "rail_terminal",
    "estacion de tren":     "rail_terminal",
    "estación de tren":     "rail_terminal",
    "rail_yard":            "rail_terminal",

    # --- road_node (nodo vial genérico) ---
    "road_node":            "road_node",
    "nodo vial":            "road_node",
    "parada":               "road_node",
    "stop":                 "road_node",

    # --- client / punto de entrega ---
    "client":               "client",
    "cliente":              "client",
    "customer":             "client",
    "delivery_point":       "client",
    "punto de entrega":     "client",

    # --- supplier / proveedor ---
    "supplier":             "supplier",
    "proveedor":            "supplier",
    "vendor":               "supplier",
}

# Conjunto de valores canónicos válidos (para validación rápida)
CANONICAL_STATION_TYPES: frozenset[str] = frozenset(CANONICAL_STATION_MAP.values())


def normalize_station_type(
    raw: Optional[str],
    default: str = "warehouse",
    strict: bool = False,
) -> str:
    """
    Normaliza un string de tipo de estación al valor canónico del sistema.

    Parameters
    ----------
    raw : str | None
        Valor crudo del campo station_type tal como viene del CSV/Excel.
    default : str
        Valor canónico a retornar si el input es None o vacío.
    strict : bool
        Si True, lanza ValueError cuando el string no se puede mapear.
        Si False (default), retorna el valor en lowercase sin modificar
        y emite un log de warning.

    Returns
    -------
    str
        Valor canónico normalizado.

    Raises
    ------
    ValueError
        Solo si strict=True y no se encuentra un mapeo.

    Examples
    --------
    >>> normalize_station_type("Deposito")
    'warehouse'
    >>> normalize_station_type("DC")
    'warehouse'
    >>> normalize_station_type(None)
    'warehouse'
    >>> normalize_station_type("unknown_type", strict=False)
    'unknown_type'
    """
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return default

    cleaned = raw.strip().lower()

    canonical = CANONICAL_STATION_MAP.get(cleaned)
    if canonical is not None:
        return canonical

    # Valor no mapeado
    if strict:
        raise ValueError(
            f"Tipo de estación desconocido: '{raw}'. "
            f"Valores canónicos válidos: {sorted(CANONICAL_STATION_TYPES)}"
        )

    logger.warning(
        "station_type '%s' no tiene mapeo canónico, se usará tal cual: '%s'. "
        "Considere agregarlo a CANONICAL_STATION_MAP.",
        raw, cleaned,
    )
    return cleaned


def is_canonical(station_type: str) -> bool:
    """Verifica si un station_type ya es un valor canónico conocido."""
    return station_type in CANONICAL_STATION_TYPES

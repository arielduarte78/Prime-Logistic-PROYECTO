# src/bloque1/config.py
import os
from typing import Dict

def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default

# Umbral global por defecto (toneladas) para validaciones muy grandes
MAX_CAPACITY = _env_float("PRIME_MAX_CAPACITY", 1e7)

# Umbrales por modo de transporte (en toneladas)
MODE_MAX_CAPACITY: Dict[str, float] = {
    "ship": 80000.0,
    "boat": 80000.0,
    "barco": 80000.0,
    "truck": 56.0,
    "camion": 56.0,
    "truck_trailer": 56.0,
    "air": 102.0,
    "plane": 102.0,
    "avion": 102.0,
    "rail": 3100.0,
    "train": 3100.0,
    "tren": 3100.0,
    "default": 1e7
}

# Frecuencia relativa por modo (numérico, heurístico para Argentina)
MODE_FREQUENCY_WEIGHT: Dict[str, float] = {
    "truck": 0.60,
    "camion": 0.60,
    "air": 0.30,
    "avion": 0.30,
    "ship": 0.10,
    "barco": 0.10,
    "rail": 0.15,
    "tren": 0.15,
    "default": 0.2
}

# Velocidades promedio por modo (km/h)
MODE_AVG_SPEED_KMH: Dict[str, float] = {
    "truck": 80.0,
    "camion": 80.0,
    "ship": 30.0,
    "barco": 30.0,
    "air": 800.0,
    "avion": 800.0,
    "rail": 60.0,
    "tren": 60.0,
    "default": 50.0
}

# Multiplicadores por tipo de ruta para camiones
TRUCK_ROUTE_MULTIPLIER: Dict[str, float] = {
    "autopista": 1.0,
    "ruta_nacional": 0.85,
    "ruta_provincial": 0.7,
    "camino_rural": 0.5,
    "urban": 0.6,
    "default": 0.9
}

# Compatibilidad estación ↔ modo
MODE_ALLOWED_STATION_TYPES: Dict[str, tuple] = {
    "air": ("airport",),
    "avion": ("airport",),
    "plane": ("airport",),
    "ship": ("port", "harbor"),
    "barco": ("port", "harbor"),
    "boat": ("port", "harbor"),
    "rail": ("rail_terminal", "rail_yard"),
    "train": ("rail_terminal", "rail_yard"),
    "truck": ("road_node", "warehouse", "terminal", "depot"),
    "camion": ("road_node", "warehouse", "terminal", "depot"),
    "default": ("warehouse", "terminal", "road_node")
}

# Conversión de unidades a toneladas (normalizamos internamente a toneladas)
UNIT_CONVERSIONS_TO_TON: Dict[str, float] = {
    "ton": 1.0,
    "tons": 1.0,
    "t": 1.0,
    "tonelada": 1.0,
    "toneladas": 1.0,
    "kg": 1.0 / 1000.0,
    "kilogram": 1.0 / 1000.0,
    "lb": 0.00045359237,
    "lbs": 0.00045359237,
    "unit": 1.0,
    "units": 1.0
}

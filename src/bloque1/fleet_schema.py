# src/bloque1/fleet_schema.py
"""
Esquemas de datos para el catálogo de Flota (FLEET) — Prime Logistics v1.3.5.

Define la estructura de un vehículo de flota que reemplaza la entrada
manual de ARCS, permitiendo que el Discovery Engine genere conexiones
de forma autónoma a partir de la capacidad operativa del cliente.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import SerializableMixin

logger = logging.getLogger(__name__)

# Modos de transporte válidos para V1.3.5 (terrestres)
VALID_FLEET_MODES = frozenset({"truck", "car", "bus"})


@dataclass(frozen=True)
class FleetVehicle(SerializableMixin):
    """
    Representa un tipo de vehículo en el catálogo de flota del cliente.

    Campos
    ------
    mode : str
        Modo de transporte: "truck", "car" o "bus".
    capacity : float
        Capacidad de carga del vehículo (define K en el arco generado).
    cost_per_km : float
        Coeficiente de costo por kilómetro (define C en la matriz de costos).
    max_range_km : float
        Autonomía máxima en km (crítico para el filtro de rango geodético).
    allowed_stations : List[str]
        Tipos de estación compatibles con este vehículo
        (e.g., ["warehouse", "factory"]). Usa valores canónicos normalizados.
    vehicle_id : str, optional
        Identificador opcional para el vehículo (e.g., "FLEET_001").
    count : int
        Cantidad de unidades de este tipo de vehículo (default: 1).
    metadata : Dict[str, Any]
        Datos auxiliares (fuente, versión, notas operativas).
    """
    mode: str
    capacity: float
    cost_per_km: float
    max_range_km: float
    allowed_stations: List[str]
    vehicle_id: Optional[str] = None
    count: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalización del modo a lowercase
        if isinstance(self.mode, str):
            object.__setattr__(self, "mode", self.mode.strip().lower())

        if self.mode not in VALID_FLEET_MODES:
            raise ValueError(
                f"Modo inválido: '{self.mode}'. "
                f"Valores permitidos: {sorted(VALID_FLEET_MODES)}"
            )

        if not isinstance(self.capacity, (int, float)) or self.capacity <= 0:
            raise ValueError(
                f"Capacidad debe ser numérica y > 0, recibido: {self.capacity}"
            )

        if not isinstance(self.cost_per_km, (int, float)) or self.cost_per_km <= 0:
            raise ValueError(
                f"cost_per_km debe ser numérico y > 0, recibido: {self.cost_per_km}"
            )

        if not isinstance(self.max_range_km, (int, float)) or self.max_range_km <= 0:
            raise ValueError(
                f"max_range_km debe ser numérico y > 0, recibido: {self.max_range_km}"
            )

        if not isinstance(self.allowed_stations, list) or len(self.allowed_stations) == 0:
            raise ValueError(
                "allowed_stations debe ser una lista no vacía de tipos de estación canónicos."
            )

        # Normalizar cada estación a lowercase
        normalized = [s.strip().lower() for s in self.allowed_stations if isinstance(s, str)]
        if len(normalized) != len(self.allowed_stations):
            raise ValueError(
                "Todos los elementos de allowed_stations deben ser strings."
            )
        object.__setattr__(self, "allowed_stations", normalized)

        if not isinstance(self.count, int) or self.count < 1:
            raise ValueError(
                f"count debe ser un entero >= 1, recibido: {self.count}"
            )

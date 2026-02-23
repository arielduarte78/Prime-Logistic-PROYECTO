# src/bloque4/config.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class Stage5Config:
    """
    Configuración central para Etapa 5: tolerancias y parámetros de orquestación.
    """
    # Tolerancias de poda (V1.3)
    eps_1: float = 0.001   # supervivencia (0.1% indiferencia)
    eps_2: float = 1.0     # costo (unidad mínima de negocio; ej. 1 km o 15 minutos)

    # Límites y seguridad operacional
    max_labels_per_node: int = 1000
    max_total_labels: int = 100000
    max_iterations: int = 10_000_000

    # Pesos por defecto para rigidez (4 componentes)
    rigidity_weights: Tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)

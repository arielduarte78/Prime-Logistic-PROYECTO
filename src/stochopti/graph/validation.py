"""stochopti/graph/validation.py — Transformaciones y Validaciones Matemáticas."""

import numpy as np

CLAMP_EPSILON = 1e-7
PROBABILITY_EPSILON = 1e-9
LOG_EPSILON = 1e-9

def clamp_probabilities(phi_vector: np.ndarray) -> np.ndarray:
    """Acota probabilidades a [0, 1 - epsilon] para evitar log(0)."""
    return np.clip(np.asarray(phi_vector, dtype=float), 0.0, 1.0 - CLAMP_EPSILON)

def compute_risk_weights(phi_vector: np.ndarray) -> np.ndarray:
    """
    Transforma probabilidades de fracaso en pesos aditivos para Dijkstra.
    w = -log(1 - phi)
    """
    return -np.log1p(-phi_vector)

def validate_probabilities(phi_vector: np.ndarray, strict: bool = False) -> None:
    """Verifica que el vector de probabilidad esté en [0,1]."""
    if strict:
        if np.any(phi_vector < 0) or np.any(phi_vector > 1):
            raise ValueError("Las probabilidades deben estar en [0,1].")
        if np.any(phi_vector >= 1.0):
            raise ValueError("strict=True pero phi_vector contiene 1.0; causaría log(0).")
    else:
        if np.any(phi_vector < -PROBABILITY_EPSILON) or np.any(phi_vector > 1 + PROBABILITY_EPSILON):
            raise ValueError("Las probabilidades deben estar en [0,1].")

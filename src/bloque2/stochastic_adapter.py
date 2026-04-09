# src/bloque2/stochastic_adapter.py
"""
StochasticBayesAdapter — Capa ETL entre Bloque 2 (MonteCarloEngine)
y Bloque 3 (BayesianJudge).

Función de Transferencia Matemática:
    Por cada arista afectada con un multiplicador de estrés M, el adaptador
    inyecta "fracasos sintéticos" en la distribución Beta:

        α_degraded = α_base                        (invariante)
        β_degraded = β_base + ⌊ γ · M ⌋           (penalización)

    donde γ es un hiperparámetro de calibración (default=10.0).

    Esto desplaza la esperanza E[θ] = α/(α+β) hacia la derecha de la
    distribución de fracasos sin alterar la evidencia positiva acumulada.

Salida:
    pandas.DataFrame con columnas (u_osm, v_osm, alpha_degraded, beta_degraded)
    compatible con BayesianJudge.load_stochastic_overrides().
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("StochasticBayesAdapter")


@dataclass(frozen=True)
class AdapterConfig:
    """Hiperparámetros de calibración del adaptador."""
    gamma: float = 10.0        # Factor de conversión M → fracasos sintéticos
    min_multiplier: float = 1.0  # Umbral mínimo de M para inyectar penalización
    clamp_beta_max: float = 1e6  # Tope superior de β para evitar overflow numérico


@dataclass
class EdgeDegradation:
    """Registro intermedio de degradación por arista."""
    u_idx: int
    v_idx: int
    alpha_degraded: float
    beta_degraded: float
    source_events: List[str] = field(default_factory=list)


class StochasticBayesAdapter:
    """
    Capa de traducción entre la salida estocástica del MonteCarloEngine
    y la interfaz de ingesta del BayesianJudge.

    Protocolo:
        1. ingest(scenarios)  — carga y acumula evidencia de escenarios.
        2. to_overrides_df()  — materializa un DataFrame de overrides.
        3. El caller invoca judge.load_stochastic_overrides(df, osm_to_rx).
    """

    def __init__(
        self,
        base_alphas: Dict[Tuple[int, int], float],
        base_betas: Dict[Tuple[int, int], float],
        config: AdapterConfig | None = None,
    ) -> None:
        """
        Args:
            base_alphas: Mapa {(u, v): α_base} de los priors originales del grafo.
            base_betas:  Mapa {(u, v): β_base} de los priors originales del grafo.
            config:      Parámetros de calibración.
        """
        self._base_alphas = base_alphas
        self._base_betas = base_betas
        self._config = config or AdapterConfig()
        
        # ==============================================================
        # VECTORIZATION FAST-PATH (Zero-Copy structure alignment)
        # ==============================================================
        edges = list(self._base_alphas.keys())
        self._U = np.array([e[0] for e in edges], dtype=np.int32)
        self._V = np.array([e[1] for e in edges], dtype=np.int32)
        
        self._alphas_arr = np.array([self._base_alphas[e] for e in edges], dtype=np.float32)
        self._betas_arr = np.array([self._base_betas[e] for e in edges], dtype=np.float32)
        
        # Tensor contiguo O(E) prelocalizado
        self._failures = np.zeros(len(edges), dtype=np.float32)
        self._n_scenarios_ingested: int = 0

    def ingest(self, scenarios: Sequence[Dict[str, Any]]) -> int:
        """
        Ingiere la salida corregida del Bloque 2 utilizando máscaras
        vectoriales NumPy (SIMD) que erradican la complejidad O(E * V).
        """
        total_injections = 0

        for scenario in scenarios:
            self._n_scenarios_ingested += 1
            events = scenario.get("events", [])

            for event in events:
                multiplier = event.get("intensity_multiplier", 1.0)
                affected = event.get("affected_indices", [])

                if multiplier < self._config.min_multiplier or not affected:
                    continue

                # Función de transferencia: ⌊ γ · M ⌋
                synthetic_failures = math.floor(self._config.gamma * multiplier)

                if synthetic_failures <= 0:
                    continue

                # ==========================================================
                # O(1) PYTHON CALL TO NUMPY C-BACKEND FOR VECTOR MASKING
                # ==========================================================
                affected_arr = np.array(affected, dtype=np.int32)
                mask = np.isin(self._U, affected_arr) | np.isin(self._V, affected_arr)
                
                # Inyección SIMD masiva
                self._failures[mask] += synthetic_failures
                
                # Tracking para reportes
                injections_made = np.sum(mask)
                if injections_made > 0:
                    total_injections += int(injections_made)

        logger.info(
            "Ingested %d scenarios, accumulated %d total failure injections.",
            self._n_scenarios_ingested,
            total_injections,
        )
        return total_injections

    def to_overrides_df(self) -> pd.DataFrame:
        """
        Materializa los priors degradados vectorizados a DataFrame.
        Descartando las aristas que no sufrieron penalización matemática (Sparse approach).
        """
        if self._n_scenarios_ingested == 0:
            logger.warning("No scenarios ingested. Returning empty DataFrame.")
            return pd.DataFrame(columns=["u_osm", "v_osm", "alpha_degraded", "beta_degraded"])

        mask_affected = self._failures > 0
        
        if not np.any(mask_affected):
            return pd.DataFrame(columns=["u_osm", "v_osm", "alpha_degraded", "beta_degraded"])
            
        avg_failures = self._failures[mask_affected] / self._n_scenarios_ingested
        beta_degraded = self._betas_arr[mask_affected] + avg_failures
        
        # Clamp SIMD
        beta_degraded = np.clip(beta_degraded, 0.0, self._config.clamp_beta_max)
        
        df = pd.DataFrame({
            "u_rx": self._U[mask_affected].astype(int),
            "v_rx": self._V[mask_affected].astype(int),
            "alpha_degraded": self._alphas_arr[mask_affected],
            "beta_degraded": beta_degraded
        })

        logger.info(
            "Override DataFrame materialized: %d edges, β range [%.1f, %.1f]",
            len(df),
            df["beta_degraded"].min() if len(df) > 0 else 0.0,
            df["beta_degraded"].max() if len(df) > 0 else 0.0,
        )
        return df

    def reset(self) -> None:
        """Limpia el estado vectorial acumulado para un nuevo ciclo."""
        self._failures.fill(0.0)
        self._n_scenarios_ingested = 0
        logger.info("Adapter state reset (NumPy buffer cleared).")

    @staticmethod
    def from_graph(graph: Any, subgraph_nodes: set | None = None, config: AdapterConfig | None = None) -> "StochasticBayesAdapter":
        """
        Factory alternativo: construye el adaptador directamente desde
        un grafo rustworkx con EdgePayload adjunto.

        Args:
            graph: rx.PyDiGraph con EdgePayload en cada arista.
            subgraph_nodes: Opcionalmente iterar solo sobre un subgrafo (mejora O(1)->~30k vs 500k aristas)
            config: Parámetros de calibración opcionales.

        Returns:
            StochasticBayesAdapter inicializado con los priors del grafo.
        """
        from src.bloque1.graph_builder import EdgePayload

        base_alphas: Dict[Tuple[int, int], float] = {}
        base_betas: Dict[Tuple[int, int], float] = {}

        for u_rx, v_rx, payload in graph.weighted_edge_list():
            if subgraph_nodes is not None and (u_rx not in subgraph_nodes or v_rx not in subgraph_nodes):
                continue
            if isinstance(payload, EdgePayload):
                base_alphas[(u_rx, v_rx)] = payload.alpha_prior
                base_betas[(u_rx, v_rx)] = payload.beta_prior

        logger.info(
            "Adapter initialized from graph: %d edges extracted.",
            len(base_alphas),
        )
        return StochasticBayesAdapter(base_alphas, base_betas, config)

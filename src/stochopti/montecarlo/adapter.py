"""stochopti/montecarlo/adapter.py — Monte Carlo to Bayesian Adapter."""

import logging
import math
import numpy as np
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class AdapterConfig:
    gamma: float = 10.0
    min_multiplier: float = 1.0
    clamp_beta_max: float = 1e6

class StochasticBayesAdapter:
    """
    Traduce multiplicadores de estrés de Monte Carlo a perturbaciones
    Bayesianas mediante operaciones vectorizadas NumPy, utilizando tipos de 
    datos genéricos (str) en lugar de específicos de OpenStreetMap.
    """
    def __init__(
        self,
        base_priors: Dict[Tuple[str, str], Tuple[float, float]],
        config: Optional[AdapterConfig] = None,
    ):
        self._config = config or AdapterConfig()
        
        edges = list(base_priors.keys())
        self._edges = edges
        self._edge_to_idx = {e: i for i, e in enumerate(edges)}
        
        self._alphas_arr = np.array([base_priors[e][0] for e in edges], dtype=np.float32)
        self._betas_arr = np.array([base_priors[e][1] for e in edges], dtype=np.float32)
        
        self._failures = np.zeros(len(edges), dtype=np.float32)
        self._n_scenarios_ingested = 0

    def ingest(self, scenarios: Sequence[Dict[str, Any]], edge_extractor: Callable[[Any], List[Tuple[str, str]]]) -> int:
        """Acumula estrés sintético desde los escenarios."""
        total_injections = 0
        for scenario in scenarios:
            self._n_scenarios_ingested += 1
            events = scenario.get("events", [])
            for ev_data in events:
                multiplier = ev_data.get("intensity_multiplier", 1.0)
                if multiplier < self._config.min_multiplier:
                    continue
                    
                synthetic_failures = math.floor(self._config.gamma * multiplier)
                if synthetic_failures <= 0:
                    continue
                    
                affected_edges = edge_extractor(ev_data)
                
                indices = [self._edge_to_idx[e] for e in affected_edges if e in self._edge_to_idx]
                if indices:
                    self._failures[indices] += synthetic_failures
                    total_injections += len(indices)
                    
        logger.info(
            "Ingested %d scenarios, accumulated %d edge stress points.",
            self._n_scenarios_ingested, total_injections
        )
        return total_injections

    def to_overrides(self) -> List[Tuple[str, str, float, float]]:
        """Exporta los priors degradados listos para BayesianRiskEngine.load_stochastic_overrides()."""
        if self._n_scenarios_ingested == 0:
            return []
            
        mask = self._failures > 0
        if not np.any(mask):
            return []
            
        raw_avg_failures = self._failures[mask] / self._n_scenarios_ingested
        beta_priors = self._betas_arr[mask]
        
        damped_failures = np.log1p(raw_avg_failures) * (self._config.gamma / 2.0)
        factor_x = 4.0
        max_allowed_stress = np.maximum(beta_priors * factor_x, 3.0)
        
        dynamic_stress = np.minimum(damped_failures, max_allowed_stress)
        beta_degraded = beta_priors + dynamic_stress
        beta_degraded = np.clip(beta_degraded, 0.0, self._config.clamp_beta_max)
        
        alpha_priors = self._alphas_arr[mask]
        
        overrides = []
        affected_indices = np.where(mask)[0]
        for idx_seq, orig_idx in enumerate(affected_indices):
            u, v = self._edges[orig_idx]
            overrides.append((u, v, float(alpha_priors[idx_seq]), float(beta_degraded[idx_seq])))
            
        return overrides

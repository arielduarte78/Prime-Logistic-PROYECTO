#bayesian_judge.py
import logging
from dataclasses import dataclass
import numpy as np
import rustworkx as rx
from collections import namedtuple
from src.bloque1.graph_builder import EdgePayload
from src.bloque3.threat_loader import load_h3_threat_matrix

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("Bayesian_Judge")

FastBeta = namedtuple('FastBeta', ['alpha', 'beta'])

class BayesianJudge:
    def __init__(self, graph: rx.PyDiGraph):
        """
        Initializes the Bayesian Judge using the EdgePayload values natively attached to 
        the rustworkx Directed Graph.
        """
        self.graph = graph
        self._arc_index = {}
        self._alphas = None
        self._betas = None
        self._threat_matrix = load_h3_threat_matrix()
        self._initialize_priors()

    def _initialize_priors(self):
        """
        Extracts alpha_prior and beta_prior from every edge's EdgePayload
        and initializes internal numpy arrays for Bayesian updates.
        """
        logger.info("Initializing Bayesian Priors from rustworkx EdgePayloads (NumPy Optimized)...")
        
        # Pass 1: Count valid edges
        valid_edges_count = 0
        for _, _, payload in self.graph.weighted_edge_list():
            if isinstance(payload, EdgePayload):
                valid_edges_count += 1
                
        # Allocate contiguous arrays strictly in float32
        self._alphas = np.zeros(valid_edges_count, dtype=np.float32)
        self._betas = np.zeros(valid_edges_count, dtype=np.float32)
        
        # Pass 2: Fill allocated structures
        idx = 0
        for u_rx, v_rx, payload in self.graph.weighted_edge_list():
            if not isinstance(payload, EdgePayload):
                continue
                
            alpha = payload.alpha_prior
            beta = payload.beta_prior

            if payload.h3_index and payload.h3_index in self._threat_matrix:
                mu = self._threat_matrix[payload.h3_index]
                alpha = alpha * (1.0 - mu * 0.5)
                beta = beta * (1.0 + mu * 0.5)
                logger.debug(f"Edge {u_rx}->{v_rx} degraded by red zone mu={mu:.2f}")

            self._arc_index[(u_rx, v_rx)] = idx
            self._alphas[idx] = max(alpha, 1.0)
            self._betas[idx] = max(beta, 1.0)
            
            idx += 1
            
        logger.info(f"Successfully initialized contiguous NumPy priors for {len(self._arc_index)} operational edges.")

    def get_params(self, u: int, v: int) -> FastBeta:
        """Returns the current FastBeta for an edge."""
        idx = self._arc_index.get((u, v))
        if idx is not None:
            return FastBeta(alpha=self._alphas[idx], beta=self._betas[idx])
        return FastBeta(1.0, 1.0)
        
    def update_edge(self, u: int, v: int, successes: float, failures: float):
        """Updates the posterior Beta distribution parameters for an edge directly in the NumPy array."""
        idx = self._arc_index.get((u, v))
        if idx is not None:
            self._alphas[idx] += np.float32(successes)
            self._betas[idx] += np.float32(failures)

    def load_stochastic_overrides(self, stochastic_priors_df, osm_to_rx: dict) -> int:
        """
        Overwrite Bayesian priors with Monte Carlo degraded values.

        Args:
            stochastic_priors_df: DataFrame with columns u_osm, v_osm, alpha_degraded, beta_degraded.
            osm_to_rx: Mapping from OSM node IDs to rustworkx internal indices.

        Returns:
            Number of edges successfully updated.
        """
        updated = 0
        for row in stochastic_priors_df.itertuples(index=False):
            u_rx = osm_to_rx.get(int(row.u_osm))
            v_rx = osm_to_rx.get(int(row.v_osm))
            if u_rx is None or v_rx is None:
                continue
            pos = self._arc_index.get((u_rx, v_rx))
            if pos is not None:
                self._alphas[pos] = np.float32(row.alpha_degraded)
                self._betas[pos] = np.float32(row.beta_degraded)
                updated += 1
        logger.info(f"Stochastic overrides applied: {updated} edges updated.")
        return updated
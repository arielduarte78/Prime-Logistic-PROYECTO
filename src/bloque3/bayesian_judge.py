#bayesian_judge.py
"""
Bayesian Judge — Motor de riesgo bayesiano con trazabilidad inmutable.

ISO 27001 Control A.12.4: Cada mutación de los Priors (α, β) se firma
criptográficamente en la IntegrityChain cuando está inyectada.

La integración es opt-in por composición: si integrity_chain=None,
el Judge opera exactamente como antes (para tests y desarrollo).
"""
import hashlib
import logging
import struct
from dataclasses import dataclass
from collections import namedtuple
from typing import Optional

import numpy as np
import rustworkx as rx

from src.bloque1.graph_builder import EdgePayload
from src.bloque3.threat_loader import load_h3_threat_matrix

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("Bayesian_Judge")

FastBeta = namedtuple('FastBeta', ['alpha', 'beta'])


class BayesianJudge:
    def __init__(self, graph: rx.PyDiGraph, integrity_chain=None):
        """
        Initializes the Bayesian Judge using the EdgePayload values natively attached to 
        the rustworkx Directed Graph.

        Args:
            graph: PyDiGraph con EdgePayload en cada arista.
            integrity_chain: Opcional. IntegrityChain para audit trail HMAC-SHA256.
                             Si es None, no se registran firmas (modo dev/test).
        """
        self.graph = graph
        self._arc_index = {}
        self._alphas = None
        self._betas = None
        self._threat_matrix = load_h3_threat_matrix()
        self._integrity = integrity_chain
        self._initialize_priors()

    def __deepcopy__(self, memo):
        import copy
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if k == '_integrity':
                # IntegrityChain contains a threading.Lock, share the instance
                setattr(result, k, v)
            else:
                setattr(result, k, copy.deepcopy(v, memo))
        return result

    @property
    def integrity_compromised(self) -> bool:
        """Proxy al estado de integridad de la cadena HMAC."""
        if self._integrity is None:
            return False
        return self._integrity.compromised

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

        # ISO 27001 A.12.4: Firma del estado inicial (GENESIS)
        if self._integrity is not None:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("INIT", state_digest)
            logger.info("IntegrityChain: INIT entry signed for %d edges.", len(self._arc_index))

    def get_params(self, u: int, v: int) -> FastBeta:
        """Returns the current FastBeta for an edge."""
        idx = self._arc_index.get((u, v))
        if idx is not None:
            return FastBeta(alpha=self._alphas[idx], beta=self._betas[idx])
        return FastBeta(1.0, 1.0)
        
    def update_edge(self, u: int, v: int, successes: float, failures: float):
        """
        Updates the posterior Beta distribution parameters for an edge
        directly in the NumPy array.
        
        ISO 27001 A.12.4: Firma HMAC de la mutación individual.
        CISO Directive: struct.pack usa big-endian (>) para portabilidad.
        """
        idx = self._arc_index.get((u, v))
        if idx is not None:
            self._alphas[idx] += np.float32(successes)
            self._betas[idx] += np.float32(failures)

            # Firma de mutación individual
            if self._integrity is not None:
                # Big-endian (>): 2x unsigned int (u, v) + 2x float (α_new, β_new)
                digest = hashlib.sha256(
                    struct.pack(">IIff", u, v,
                                float(self._alphas[idx]),
                                float(self._betas[idx]))
                ).digest()
                self._integrity.append("UPDATE_EDGE", digest)

    def load_stochastic_overrides(self, stochastic_priors_df, osm_to_rx: dict) -> int:
        """
        Overwrite Bayesian priors with Monte Carlo degraded values.

        Args:
            stochastic_priors_df: DataFrame with columns u_osm, v_osm, alpha_degraded, beta_degraded.
            osm_to_rx: Mapping from OSM node IDs to rustworkx internal indices.

        Returns:
            Number of edges successfully updated.
        
        ISO 27001 A.12.4: Firma HMAC del estado completo post-override.
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

        # Firma del estado completo post-override
        if self._integrity is not None:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("STOCHASTIC_OVERRIDE", state_digest)
            logger.info("IntegrityChain: STOCHASTIC_OVERRIDE entry signed (%d edges).", updated)

        return updated

    def activate_emergency_mode(self):
        """
        Modo Conservador: revierte todos los priors a α=1.0, β=1.0 (uninformative).
        Se activa cuando la cadena de integridad detecta adulteración.
        """
        logger.critical(
            "EMERGENCY MODE ACTIVATED: Reverting all %d priors to conservative defaults (α=1, β=1).",
            len(self._arc_index)
        )
        self._alphas[:] = np.float32(1.0)
        self._betas[:] = np.float32(1.0)

        if self._integrity is not None:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("EMERGENCY_REVERT", state_digest)
"""stochopti/bayesian/engine.py — Bayesian Risk Engine."""

import hashlib
import logging
import struct
import atexit
from multiprocessing import shared_memory
from collections import namedtuple
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from stochopti.core.types import BetaPrior, GraphSpec
from stochopti.core.protocols import PriorProvider, ThreatProvider
from stochopti.bayesian.integrity import IntegrityChain
from stochopti.core.exceptions import SharedMemoryCorruptionError

logger = logging.getLogger(__name__)

FastBeta = namedtuple('FastBeta', ['alpha', 'beta'])

class SharedBayesianState:
    """
    Gestiona el bloque de memoria compartida para los arreglos base _alphas y _betas.
    Creado una única vez por el proceso maestro.
    """
    def __init__(self, num_edges: int):
        self.num_edges = num_edges
        self.nbytes = num_edges * np.dtype(np.float64).itemsize
        
        # Bloques de memoria compartida
        self.shm_alphas = shared_memory.SharedMemory(create=True, size=self.nbytes)
        self.shm_betas = shared_memory.SharedMemory(create=True, size=self.nbytes)
        
        # Vistas NumPy vinculadas al buffer compartido
        self.alphas_base = np.ndarray((num_edges,), dtype=np.float64, buffer=self.shm_alphas.buf)
        self.betas_base = np.ndarray((num_edges,), dtype=np.float64, buffer=self.shm_betas.buf)
        
        # Inicialización de priors uniformes Beta(2, 2)
        self.alphas_base.fill(2.0)
        self.betas_base.fill(2.0)
        
        self._closed = False
        atexit.register(self.close_and_unlink)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_and_unlink()

    def close_and_unlink(self):
        if not self._closed:
            try:
                self.shm_alphas.close()
                self.shm_alphas.unlink()
            except FileNotFoundError:
                pass
            try:
                self.shm_betas.close()
                self.shm_betas.unlink()
            except FileNotFoundError:
                pass
            self._closed = True


class EphemeralWorkerBayesianEngine:
    """
    Instanciado dentro de cada proceso worker. Mantiene una vista de solo lectura
    de la memoria compartida y almacena mutaciones en una estructura dispersa.
    """
    def __init__(self, shm_alphas_name: str, shm_betas_name: str, num_edges: int):
        try:
            self.shm_a = shared_memory.SharedMemory(name=shm_alphas_name)
            self.shm_b = shared_memory.SharedMemory(name=shm_betas_name)
        except Exception as e:
            raise SharedMemoryCorruptionError(f"Failed to attach to shared memory: {e}")
        
        self._alphas_base = np.ndarray((num_edges,), dtype=np.float64, buffer=self.shm_a.buf)
        self._betas_base = np.ndarray((num_edges,), dtype=np.float64, buffer=self.shm_b.buf)
        
        # Inmutabilidad en Shared Memory para prevenir corrupción accidental
        self._alphas_base.flags.writeable = False
        self._betas_base.flags.writeable = False
        
        # Almacenamiento local de mutaciones (k << |E|)
        self._sparse_deltas: Dict[int, Tuple[float, float]] = {}

    def update_edge_local(self, edge_idx: int, successes: float, failures: float) -> None:
        """Registra la perturbación estocástica solo en el delta local del worker."""
        current_s, current_f = self._sparse_deltas.get(edge_idx, (0.0, 0.0))
        self._sparse_deltas[edge_idx] = (current_s + successes, current_f + failures)

    def get_effective_parameters(self, edge_idx: int) -> Tuple[float, float]:
        """Consulta en O(1): base compartida + delta local."""
        delta_s, delta_f = self._sparse_deltas.get(edge_idx, (0.0, 0.0))
        alpha = self._alphas_base[edge_idx] + delta_s
        beta = self._betas_base[edge_idx] + delta_f
        return alpha, beta

    def sample_edge_risk_vector(self, perturbed_edge_indices: Sequence[int]) -> np.ndarray:
        """
        Vectoriza el muestreo de riesgo para las aristas evaluadas:
        E[p] = alpha / (alpha + beta)
        """
        if not perturbed_edge_indices:
            return np.array([], dtype=np.float64)
            
        alphas = np.array([self.get_effective_parameters(i)[0] for i in perturbed_edge_indices], dtype=np.float64)
        betas = np.array([self.get_effective_parameters(i)[1] for i in perturbed_edge_indices], dtype=np.float64)
        return alphas / (alphas + betas)

    def cleanup(self):
        self.shm_a.close()
        self.shm_b.close()


class BayesianRiskEngine:
    """Motor de riesgo bayesiano optimizado con NumPy y audit trail HMAC. (Legacy standalone mode supported)"""
    def __init__(
        self,
        graph: Optional[GraphSpec] = None,
        integrity_chain: Optional[IntegrityChain] = None,
        prior_provider: Optional[PriorProvider] = None,
        threat_provider: Optional[ThreatProvider] = None,
        default_prior: Optional[BetaPrior] = None,
    ):
        self.graph = graph
        self._arc_index: Dict[Tuple[str, str], int] = {}
        self._alphas: Optional[np.ndarray] = None
        self._betas: Optional[np.ndarray] = None
        self._integrity = integrity_chain
        self._node_edges: Dict[str, List[Tuple[str, str]]] = {}
        
        self._prior_provider = prior_provider
        self._threat_provider = threat_provider
        self._default_prior = default_prior or BetaPrior(2.0, 2.0)
        self._standalone = graph is None
        
        if self._standalone:
            self._alphas = np.empty(0, dtype=np.float32)
            self._betas = np.empty(0, dtype=np.float32)
            logger.info("BayesianRiskEngine initialized in STANDALONE mode.")
        else:
            self._initialize_priors()

    def spawn_ephemeral_clone(self) -> "BayesianRiskEngine":
        """Clonación Zero-Copy de referencias para simulaciones (Legacy)."""
        cls = self.__class__
        clone = cls.__new__(cls)
        
        clone.graph = self.graph
        clone._arc_index = self._arc_index
        clone._node_edges = self._node_edges
        clone._integrity = self._integrity
        clone._prior_provider = self._prior_provider
        clone._threat_provider = self._threat_provider
        clone._default_prior = self._default_prior
        clone._standalone = self._standalone
        
        clone._alphas = self._alphas.copy() if self._alphas is not None else None
        clone._betas = self._betas.copy() if self._betas is not None else None
        
        return clone

    @property
    def integrity_compromised(self) -> bool:
        if self._integrity is None:
            return False
        return self._integrity.compromised

    def _initialize_priors(self):
        if self.graph is None:
            return

        valid_edges = len(self.graph.edges)
        self._alphas = np.zeros(valid_edges, dtype=np.float32)
        self._betas = np.zeros(valid_edges, dtype=np.float32)

        priors_map = self._prior_provider.get_priors() if self._prior_provider else {}

        idx = 0
        for edge in self.graph.edges:
            prior = priors_map.get((edge.source, edge.target), self._default_prior)
            alpha = prior.alpha
            beta = prior.beta
            
            if self._threat_provider:
                mu = self._threat_provider.get_threat_level(edge)
                alpha = alpha * (1.0 - mu * 0.5)
                beta = beta * (1.0 + mu * 0.5)
                
            self._arc_index[(edge.source, edge.target)] = idx
            self._alphas[idx] = max(alpha, 1.0)
            self._betas[idx] = max(beta, 1.0)
            
            self._node_edges.setdefault(edge.source, []).append((edge.source, edge.target))
            self._node_edges.setdefault(edge.target, []).append((edge.source, edge.target))
            
            idx += 1

        if self._integrity is not None:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("INIT", state_digest)

    def get_params(self, u: str, v: str) -> FastBeta:
        idx = self._arc_index.get((u, v))
        if idx is not None and self._alphas is not None and self._betas is not None:
            return FastBeta(alpha=self._alphas[idx], beta=self._betas[idx])
        return FastBeta(self._default_prior.alpha, self._default_prior.beta)

    def update_edge(self, u: str, v: str, successes: float, failures: float):
        idx = self._arc_index.get((u, v))
        if idx is not None and self._alphas is not None and self._betas is not None:
            self._alphas[idx] += np.float32(successes)
            self._betas[idx] += np.float32(failures)

            if self._integrity is not None:
                # Se utiliza codificación estable y trunca a 8 bytes
                u_bytes = str(u).encode('utf-8')[:8].ljust(8, b'\0')
                v_bytes = str(v).encode('utf-8')[:8].ljust(8, b'\0')
                digest = hashlib.sha256(
                    u_bytes + v_bytes + struct.pack(">ff", float(self._alphas[idx]), float(self._betas[idx]))
                ).digest()
                self._integrity.append("UPDATE_EDGE", digest)

    def batch_observe(
        self,
        batched_data: Sequence[Tuple[Any, Mapping[str, Any]]],
    ) -> None:
        if self._alphas is None or self._betas is None:
            return

        total_updates = 0
        for audit_record, payload in batched_data:
            success = getattr(audit_record, 'success', False)
            successes = 1.0 if success else 0.0
            failures = 0.0 if success else 1.0

            affected_edges = payload.get("affected_edges", None)

            if affected_edges:
                for u, v in affected_edges:
                    self.update_edge(u, v, successes, failures)
                    total_updates += 1
            else:
                if len(self._arc_index) > 0:
                    self._alphas += np.float32(successes)
                    self._betas += np.float32(failures)
                    total_updates += len(self._arc_index)

        if self._integrity is not None and total_updates > 0:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("BATCH_OBSERVE", state_digest)
            
    def load_stochastic_overrides(self, overrides: Sequence[Tuple[str, str, float, float]]) -> int:
        """Inyecta distribuciones Monte Carlo degradadas (agnóstico a la estructura)."""
        updated = 0
        if self._alphas is None or self._betas is None:
            return updated
            
        for u, v, alpha, beta in overrides:
            idx = self._arc_index.get((u, v))
            if idx is not None:
                self._alphas[idx] = alpha
                self._betas[idx] = beta
                updated += 1
                
        if self._integrity is not None and updated > 0:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("STOCHASTIC_OVERRIDE", state_digest)

        return updated

    def arc_params(self) -> Dict[str, BetaPrior]:
        result: Dict[str, BetaPrior] = {}
        if self._alphas is None or self._betas is None:
            return result
        for (u, v), idx in self._arc_index.items():
            key = f"{u}:{v}"
            result[key] = BetaPrior(
                alpha=float(self._alphas[idx]),
                beta=float(self._betas[idx]),
            )
        return result

    def node_params(self) -> Dict[str, BetaPrior]:
        result: Dict[str, BetaPrior] = {}
        if self._alphas is None or self._betas is None:
            return result
        for node_id, edges in self._node_edges.items():
            alphas = []
            betas = []
            for u, v in edges:
                idx = self._arc_index.get((u, v))
                if idx is not None:
                    alphas.append(float(self._alphas[idx]))
                    betas.append(float(self._betas[idx]))
            if alphas:
                result[str(node_id)] = BetaPrior(
                    alpha=float(np.mean(alphas)),
                    beta=float(np.mean(betas)),
                )
        return result

    def system_params(self) -> BetaPrior:
        if self._alphas is None or self._betas is None or len(self._alphas) == 0:
            return self._default_prior
        return BetaPrior(
            alpha=float(np.mean(self._alphas)),
            beta=float(np.mean(self._betas)),
        )

    def reliability_report(self, failure_threshold: float = 0.3) -> Dict[str, Any]:
        if self._alphas is None or self._betas is None or len(self._alphas) == 0:
            return {"edges": {}, "nodes": {}, "system": {}}

        means = self._alphas / (self._alphas + self._betas)
        prob_failures = 1.0 - means

        mask = prob_failures > failure_threshold
        risky_indices = set(np.where(mask)[0].tolist())

        edges_report = {}
        if risky_indices:
            for (u, v), idx in self._arc_index.items():
                if idx in risky_indices:
                    edges_report[f"{u}:{v}"] = {
                        "prob_failure": float(prob_failures[idx]),
                        "impact_mean": float(means[idx]),
                    }

        sys_params = self.system_params()
        system_report = {
             "prob_failure": 1.0 - sys_params.mean,
             "impact_mean": sys_params.mean,
        }

        return {
            "edges": edges_report,
            "nodes": {},
            "system": system_report,
        }

    def activate_emergency_mode(self):
        if self._alphas is None or self._betas is None: return
        self._alphas[:] = np.float32(1.0)
        self._betas[:] = np.float32(1.0)

        if self._integrity is not None:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("EMERGENCY_REVERT", state_digest)

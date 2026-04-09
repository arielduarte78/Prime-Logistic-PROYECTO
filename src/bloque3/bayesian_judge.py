# bayesian_judge.py
"""
Bayesian Judge — Motor de riesgo bayesiano con trazabilidad inmutable.

ISO 27001 Control A.12.4: Cada mutación de los Priors (α, β) se firma
criptográficamente en la IntegrityChain cuando está inyectada.

La integración es opt-in por composición: si integrity_chain=None,
el Judge opera exactamente como antes (para tests y desarrollo).

Exporta:
    - BayesianJudge  : clase principal (graph-backed)
    - BetaParams     : contenedor tipado de (α, β) con .mean
    - PriorConfig    : configuración default de priors para modo standalone
    - FastBeta       : namedtuple ligero para hot-path de Bloque 4
"""
import hashlib
import logging
import struct
from dataclasses import dataclass
from collections import namedtuple
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import rustworkx as rx

from src.bloque1.graph_builder import EdgePayload
from src.bloque3.threat_loader import load_h3_threat_matrix

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("Bayesian_Judge")

FastBeta = namedtuple('FastBeta', ['alpha', 'beta'])


# ============================================================================
# TIPOS EXPORTABLES (consumidos por InferenceEngine)
# ============================================================================

@dataclass(frozen=True)
class BetaParams:
    """Parámetros de una distribución Beta con esperanza calculada."""
    alpha: float
    beta: float

    @property
    def mean(self) -> float:
        """E[θ] = α / (α + β)."""
        denom = self.alpha + self.beta
        if denom <= 0:
            return 0.0
        return self.alpha / denom


@dataclass(frozen=True)
class PriorConfig:
    """Configuración de priors por defecto para modo standalone."""
    alpha: float = 2.0
    beta: float = 2.0


# ============================================================================
# BAYESIAN JUDGE
# ============================================================================

class BayesianJudge:
    def __init__(
        self,
        graph: Optional[rx.PyDiGraph] = None,
        integrity_chain: Any = None,
        *,
        prior: Optional[PriorConfig] = None,
    ):
        """
        Inicializa el Bayesian Judge.

        Modos de operación:
            1. Graph-backed (producción): se pasa un PyDiGraph con EdgePayload.
               Los priors se extraen directamente de las aristas.
            2. Standalone (InferenceEngine): se pasa prior=PriorConfig().
               El Judge arranca vacío y acumula evidencia via batch_observe().

        Args:
            graph: PyDiGraph con EdgePayload en cada arista (modo producción).
            integrity_chain: Opcional. IntegrityChain para audit trail HMAC-SHA256.
            prior: PriorConfig para modo standalone (sin grafo).
        """
        self.graph = graph
        self._arc_index: Dict[Tuple[int, int], int] = {}
        self._alphas: Optional[np.ndarray] = None
        self._betas: Optional[np.ndarray] = None
        self._integrity = integrity_chain

        # Índices reversos para reportes por nodo
        self._node_edges: Dict[int, List[Tuple[int, int]]] = {}

        # Modo standalone: priors uniformes, sin grafo
        self._prior_config = prior or PriorConfig()
        self._standalone = graph is None

        if self._standalone:
            # Inicializar arrays vacíos; se llenarán via batch_observe
            self._alphas = np.empty(0, dtype=np.float32)
            self._betas = np.empty(0, dtype=np.float32)
            self._threat_matrix: Dict[str, float] = {}
            logger.info("BayesianJudge initialized in STANDALONE mode (prior α=%.1f, β=%.1f).",
                        self._prior_config.alpha, self._prior_config.beta)
        else:
            self._threat_matrix = load_h3_threat_matrix()
            self._initialize_priors()

    def spawn_ephemeral_clone(self) -> "BayesianJudge":
        """
        Patrón Flyweight (Zero-Copy): Instancia un clon efímero copiando 
        únicamente los tensores estocásticos mutables a nivel de C (NumPy).
        El resto de las estructuras masivas (el grafo, índices, amenaza) se
        pasan estrictamente por puntero ($O(1)$ en RAM).
        """
        cls = self.__class__
        clone = cls.__new__(cls)
        
        # Referencias O(1)
        clone.graph = self.graph
        clone._arc_index = self._arc_index
        clone._node_edges = self._node_edges
        clone._integrity = self._integrity
        clone._threat_matrix = self._threat_matrix
        clone._prior_config = self._prior_config
        clone._standalone = self._standalone
        
        # Copia física profunda (O(E)) solo para los tensores
        clone._alphas = self._alphas.copy() if self._alphas is not None else None
        clone._betas = self._betas.copy() if self._betas is not None else None
        
        return clone

    @property
    def integrity_compromised(self) -> bool:
        """Proxy al estado de integridad de la cadena HMAC."""
        if self._integrity is None:
            return False
        return self._integrity.compromised

    # ================================================================
    # INICIALIZACIÓN DE PRIORS (Graph-backed)
    # ================================================================

    def _initialize_priors(self):
        """
        Extracts alpha_prior and beta_prior from every edge's EdgePayload
        and initializes internal numpy arrays for Bayesian updates.
        """
        if self.graph is None:
            return

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

            # Índice reverso para node_params()
            self._node_edges.setdefault(u_rx, []).append((u_rx, v_rx))
            self._node_edges.setdefault(v_rx, []).append((u_rx, v_rx))

            idx += 1

        logger.info(f"Successfully initialized contiguous NumPy priors for {len(self._arc_index)} operational edges.")

        # ISO 27001 A.12.4: Firma del estado inicial (GENESIS)
        if self._integrity is not None:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("INIT", state_digest)
            logger.info("IntegrityChain: INIT entry signed for %d edges.", len(self._arc_index))

    # ================================================================
    # CONSULTA DE PARÁMETROS (Hot-path Bloque 4)
    # ================================================================

    def get_params(self, u: int, v: int) -> FastBeta:
        """Returns the current FastBeta for an edge."""
        idx = self._arc_index.get((u, v))
        if idx is not None:
            return FastBeta(alpha=self._alphas[idx], beta=self._betas[idx])
        return FastBeta(1.0, 1.0)

    # ================================================================
    # ACTUALIZACIÓN INDIVIDUAL (Granular)
    # ================================================================

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

    # ================================================================
    # INGESTA MASIVA (Interfaz para InferenceEngine)
    # ================================================================

    def batch_observe(
        self,
        batched_data: Sequence[Tuple[Any, Mapping[str, Any]]],
    ) -> None:
        """
        Ingesta masiva de evidencia empírica desde el auditor forense.

        Cada elemento de batched_data es una tupla (AuditRecord, payload_dict).
        El AuditRecord contiene:
            - scenario_id: str
            - success: bool       → si True, inyecta 1 éxito; si False, 1 fracaso.
            - reasons: Tuple[str, ...]
            - metrics: Dict[str, Any]

        El payload_dict puede contener:
            - "affected_edges": List[Tuple[int, int]]  → aristas específicas.

        Si no hay affected_edges, la observación se aplica al sistema completo.
        """
        if self._alphas is None or self._betas is None:
            logger.warning("batch_observe called before priors initialized; no-op.")
            return

        total_updates = 0

        for audit_record, payload in batched_data:
            successes = 1.0 if audit_record.success else 0.0
            failures = 0.0 if audit_record.success else 1.0

            affected_edges = payload.get("affected_edges", None)

            if affected_edges:
                # Actualizar solo las aristas específicas
                for u, v in affected_edges:
                    self.update_edge(u, v, successes, failures)
                    total_updates += 1
            else:
                # Observación sistémica: aplicar a TODAS las aristas
                if len(self._arc_index) > 0:
                    self._alphas += np.float32(successes)
                    self._betas += np.float32(failures)
                    total_updates += len(self._arc_index)

        logger.info("batch_observe: %d edge updates from %d audit records.",
                     total_updates, len(batched_data))

        # Firma post-batch
        if self._integrity is not None and total_updates > 0:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("BATCH_OBSERVE", state_digest)

    # ================================================================
    # STOCHASTIC OVERRIDES (Bloque 2 → Bloque 3 via Adapter)
    # ================================================================

    def load_stochastic_overrides(self, stochastic_priors_df: pd.DataFrame, osm_to_rx: dict) -> int:
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
        u_arr = stochastic_priors_df["u_rx"].values.astype(int)
        v_arr = stochastic_priors_df["v_rx"].values.astype(int)
        alpha_arr = stochastic_priors_df["alpha_degraded"].values.astype(np.float32)
        beta_arr = stochastic_priors_df["beta_degraded"].values.astype(np.float32)
        
        posiciones = [self._arc_index.get((u_arr[i], v_arr[i])) for i in range(len(u_arr))]
        mask = [p is not None for p in posiciones]
        valid_pos = [p for p in posiciones if p is not None]
        
        if valid_pos:
            self._alphas[valid_pos] = alpha_arr[mask]
            self._betas[valid_pos] = beta_arr[mask]
            updated = len(valid_pos)
        else:
            updated = 0
        logger.info(f"Stochastic overrides applied: {updated} edges updated.")

        # Firma del estado completo post-override
        if self._integrity is not None:
            state_digest = hashlib.sha256(
                self._alphas.tobytes() + self._betas.tobytes()
            ).digest()
            self._integrity.append("STOCHASTIC_OVERRIDE", state_digest)
            logger.info("IntegrityChain: STOCHASTIC_OVERRIDE entry signed (%d edges).", updated)

        return updated

    # ================================================================
    # REPORTERÍA (Interfaz para InferenceEngine)
    # ================================================================

    def arc_params(self) -> Dict[str, BetaParams]:
        """
        Retorna los parámetros Beta actuales por arista.

        Returns:
            Dict con clave "u:v" y valor BetaParams para cada arista indexada.
        """
        result: Dict[str, BetaParams] = {}
        for (u, v), idx in self._arc_index.items():
            key = f"{u}:{v}"
            result[key] = BetaParams(
                alpha=float(self._alphas[idx]),
                beta=float(self._betas[idx]),
            )
        return result

    def node_params(self) -> Dict[str, BetaParams]:
        """
        Retorna los parámetros Beta agregados por nodo.

        Para cada nodo, se promedian los α y β de todas las aristas
        incidentes (entrantes + salientes), produciendo un estimador
        de la confiabilidad nodal.

        Returns:
            Dict con clave str(node_id) y valor BetaParams.
        """
        result: Dict[str, BetaParams] = {}
        for node_id, edges in self._node_edges.items():
            alphas: List[float] = []
            betas: List[float] = []
            for u, v in edges:
                idx = self._arc_index.get((u, v))
                if idx is not None:
                    alphas.append(float(self._alphas[idx]))
                    betas.append(float(self._betas[idx]))
            if alphas:
                result[str(node_id)] = BetaParams(
                    alpha=float(np.mean(alphas)),
                    beta=float(np.mean(betas)),
                )
        return result

    def system_params(self) -> BetaParams:
        """
        Retorna los parámetros Beta agregados del sistema completo.

        Calcula la media aritmética de todos los α y β del grafo,
        dando un estimador de la confiabilidad sistémica global.

        Returns:
            BetaParams con los promedios globales.
        """
        if self._alphas is None or len(self._alphas) == 0:
            return BetaParams(
                alpha=self._prior_config.alpha,
                beta=self._prior_config.beta,
            )
        return BetaParams(
            alpha=float(np.mean(self._alphas)),
            beta=float(np.mean(self._betas)),
        )

    def reliability_report(self, failure_threshold: float = 0.3) -> Dict[str, Any]:
        """
        Consolida el estado actual de la red en un reporte estructurado.
        """
        if self._alphas is None or len(self._alphas) == 0:
            return {"edges": {}, "nodes": {}, "system": {}}

        # 1. Operaciones Vectorizadas NumPy (O(1) a nivel intérprete)
        means = self._alphas / (self._alphas + self._betas)
        prob_failures = 1.0 - means

        # 2. Filtrado de aristas en riesgo (> threshold)
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

        logger.info(
            "Reliability report generated: %d risky edges found (threshold=%.2f), system E[θ]=%.4f",
            len(edges_report), failure_threshold, sys_params.mean,
        )

        return {
            "edges": edges_report,
            "nodes": {},  # Lazyfied y omitido para abatir O(N) de CPU time
            "system": system_report,
        }

    # ================================================================
    # MODO EMERGENCIA
    # ================================================================

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
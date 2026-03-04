#bayesian_judge.py
import logging
from dataclasses import dataclass
import rustworkx as rx
from src.bloque1.graph_builder import EdgePayload
from src.bloque3.threat_loader import load_h3_threat_matrix

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("Bayesian_Judge")

@dataclass
class BetaParams:
    """Mutable parameters for the Beta distribution updated during inference."""
    alpha: float
    beta: float

    def update(self, successes: float, failures: float):
        self.alpha += successes
        self.beta += failures

class BayesianJudge:
    def __init__(self, graph: rx.PyDiGraph):
        """
        Initializes the Bayesian Judge using the EdgePayload values natively attached to 
        the rustworkx Directed Graph.
        """
        self.graph = graph
        self._arc_params = {}
        self._threat_matrix = load_h3_threat_matrix()
        self._initialize_priors()

    def _initialize_priors(self):
        """
        Extracts alpha_prior and beta_prior from every edge's EdgePayload
        and initializes the mutable _arc_params dictionary for Bayesian updates.
        """
        logger.info("Initializing Bayesian Priors from rustworkx EdgePayloads...")
        
        # Iterating over explicitly weighted edges in rustworkx
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

            # The prior is not uniform anymore; it's informed by the ETL Phase 1 and Threat Matrix
            self._arc_params[(u_rx, v_rx)] = BetaParams(
                alpha=max(alpha, 1.0),
                beta=max(beta, 1.0)
            )
            
        logger.info(f"Successfully initialized priors for {len(self._arc_params)} operational edges.")

    def get_params(self, u: int, v: int) -> BetaParams:
        """Returns the current BetaParams for an edge."""
        return self._arc_params.get((u, v), BetaParams(1.0, 1.0))
        
    def update_edge(self, u: int, v: int, successes: float, failures: float):
        """Updates the posterior Beta distribution parameters for an edge."""
        if (u, v) in self._arc_params:
            self._arc_params[(u, v)].update(successes, failures)
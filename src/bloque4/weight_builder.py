#src/bloque4/weight_builder.py
import logging
import math
from dataclasses import dataclass
from typing import List, Dict
import rustworkx as rx
from src.bloque1.graph_builder import EdgePayload
from src.bloque3.bayesian_judge import BayesianJudge

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("Weight_Builder")

@dataclass(frozen=True)
class Edge:
    """
    Final Edge artifact expected by the native Pareto engine (Block 4)
    """
    u: int
    v: int
    length: float
    w_expected_cost: float
    w_survival: float
    highway_type: str

def build_pareto_edges(graph: rx.PyDiGraph, judge: BayesianJudge) -> List[Edge]:
    """
    Reads the rustworkx graph populated post-Monte Carlo and creates the
    final operational schema.Edge objects for the MOEA setting.
    This preserves the intact mathematical integrity of Block 4.
    """
    logger.info("Building final schema.Edge objects for the Pareto Multiobjective Optimizer...")
    pareto_edges = []
    
    # Iterate over the graph exactly once
    for u_rx, v_rx, payload in graph.weighted_edge_list():
        if not isinstance(payload, EdgePayload):
            continue
            
        # Get exact updated prior from Block 3 Bayesian Inference
        beta_params = judge.get_params(u_rx, v_rx)
        
        # Calculate Reliability/Survival based on Beta Posterior Expected Value
        # E(Beta) = alpha / (alpha + beta)
        survival_probability = beta_params.alpha / (beta_params.alpha + beta_params.beta)
        
        # Transform multiplicative survival probability into an additive logarithmic penalty
        w_survival = -math.log(max(survival_probability, 1e-9))
        
        # We assume Expected Cost as purely geometric for this architecture scope
        # Incorporating the expected frictional damage in case of failure:
        p_failure = 1.0 - survival_probability
        expected_cost = payload.length + (p_failure * payload.length)
        
        edge = Edge(
            u=u_rx,  # Keeping rustworkx internal pointers for speed in Block 4 labels
            v=v_rx,
            length=payload.length,
            w_expected_cost=expected_cost,
            w_survival=w_survival,
            highway_type=payload.highway
        )
        pareto_edges.append(edge)
        
    logger.info(f"Successfully constructed {len(pareto_edges)} objects for Pareto Engine.")
    return pareto_edges

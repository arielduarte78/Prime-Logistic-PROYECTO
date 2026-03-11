#src/bloque4/lazy_graph.py
import math
from typing import Iterator, Set, Dict, Any, TYPE_CHECKING
from src.bloque4.schema import Edge, Node
from src.bloque1.graph_builder import EdgePayload
from src.block5.speed_profile_loader import get_h3_parent, get_velocity_multiplier
from src.bloque4.cost_calculator import compute_edge_cost

if TYPE_CHECKING:
    import rustworkx as rx
    from src.bloque3.bayesian_judge import BayesianJudge
    from src.config.settings import CostSettings

class LazyEdgeIterable:
    def __init__(self, lazy_graph: 'LazyEdgeView'):
        self.lg = lazy_graph

    def __iter__(self) -> Iterator[Edge]:
        for i, (u_rx, v_rx, payload) in enumerate(self.lg.rx_graph.weighted_edge_list()):
            if v_rx not in self.lg.allowed_nodes or u_rx not in self.lg.allowed_nodes:
                continue

            if not isinstance(payload, EdgePayload):
                continue

            beta_params = self.lg.judge.get_params(u_rx, v_rx)
            p_survival = beta_params.alpha / (beta_params.alpha + beta_params.beta)
            p_failure = 1.0 - p_survival
            w_survival = -math.log(max(p_survival, 1e-9))

            dist_km = payload.length / 1000.0
            
            # V1.4.10: Velocidad efectiva con multiplicador de trafico
            h3_parent = get_h3_parent(payload.h3_index)
            multiplier = get_velocity_multiplier(
                self.lg.speed_profiles, payload.highway, h3_parent, self.lg.departure_hour
            )
            effective_velocity = self.lg.cost_env.velocidad_comercial_kmh * multiplier
            time_hr = dist_km / effective_velocity
            
            # Use unified calculator logic default (weight is total cost w_expected_cost)
            # The archetype passed doesn't matter since the risk multipliers are computed inside
            
            w_expected_cost = compute_edge_cost(
                payload=payload,
                u_rx=u_rx,
                v_rx=v_rx,
                cost_env=self.lg.cost_env,
                threat_matrix=self.lg.threat_matrix,
                judge=self.lg.judge,
                departure_hour=self.lg.departure_hour,
                speed_profiles=self.lg.speed_profiles,
                archetype='tanque' # Just to comply with signature, unused directly here
            )
            # Override for absolute parity
            lambda_cost, lambda_risk = 1.0, 0.0
            financial_cost_ars = w_expected_cost # this is the base we get from pure calc
            
            # Recalculate pure financial cost manually for schema parity or pass 1.0 archetype
            w_expected_cost = compute_edge_cost(
                payload=payload,
                u_rx=u_rx,
                v_rx=v_rx,
                cost_env=self.lg.cost_env,
                threat_matrix=self.lg.threat_matrix,
                judge=self.lg.judge,
                departure_hour=self.lg.departure_hour,
                speed_profiles=self.lg.speed_profiles,
                archetype='none' # using 1.0 cost / 0 risk for raw expected cost
            )

            yield Edge(
                edge_id=f"{u_rx}_{v_rx}_{i}",
                source=str(u_rx),
                target=str(v_rx),
                cost=w_expected_cost,
                distance=payload.length,
                mode="truck",
                time=time_hr * 3600,
                risk=p_failure,
                risk_weight=w_survival,
                w_survival=w_survival,
                w_expected_cost=w_expected_cost
            )

class LazyEdgeView:
    """
    Duck-types the Graph schema from legacy code.
    Lazily instantiates Edge objects on the fly, applying the provided
    user's economic profile.
    """
    def __init__(
        self,
        rx_graph: 'rx.PyDiGraph',
        allowed_nodes: Set[int],
        cost_env: Any, # Usually CostSettings or an object simulating it
        threat_matrix: Dict[str, float],
        ruta_tipica_km: float,
        judge: 'BayesianJudge',
        departure_hour: int = 12,
        speed_profiles: dict = None
    ):
        self.rx_graph = rx_graph
        self.allowed_nodes = allowed_nodes
        self.cost_env = cost_env
        self.threat_matrix = threat_matrix
        self.ruta_tipica_km = ruta_tipica_km
        self.judge = judge
        self.departure_hour = departure_hour
        self.speed_profiles = speed_profiles if speed_profiles is not None else {}
        
        self.highway_tolls = {"motorway", "motorway_link", "trunk", "trunk_link"}

    @property
    def nodes(self) -> Iterator[Node]:
        for rx_idx in self.allowed_nodes:
            node_payload = self.rx_graph[rx_idx]
            lat = getattr(node_payload, 'lat', 0.0)
            lon = getattr(node_payload, 'lon', 0.0)
            yield Node(node_id=str(rx_idx), lat=lat, lon=lon)

    @property
    def edges(self) -> LazyEdgeIterable:
        return LazyEdgeIterable(self)

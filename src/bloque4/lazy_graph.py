#src/bloque4/lazy_graph.py
import math
from typing import Iterator, Set, Dict, Any, TYPE_CHECKING
from src.bloque4.schema import Edge, Node
from src.bloque1.graph_builder import EdgePayload

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
            time_hr = dist_km / self.lg.cost_env.velocidad_comercial_kmh
            financial_cost_ars = (dist_km * self.lg.cost_env.c_km_ars) + (time_hr * self.lg.cost_env.c_hora_ars)

            if payload.h3_index and payload.h3_index in self.lg.threat_matrix:
                mu = self.lg.threat_matrix[payload.h3_index]
                guardia_cost = time_hr * self.lg.cost_env.custodia_hora_ars * mu
                financial_cost_ars += guardia_cost

            if payload.highway in self.lg.highway_tolls:
                name_upper = payload.name.upper() if payload.name else ""
                if "25 DE MAYO" in name_upper or "PERITO MORENO" in name_upper:
                    financial_cost_ars += self.lg.cost_env.ausa_25_mayo_ars
                elif "PASEO DEL BAJO" in name_upper or "BAJO" in name_upper:
                    financial_cost_ars += self.lg.cost_env.ausa_paseo_bajo_ars
                elif ("PANAMERICANA" in name_upper or "ACCESO NORTE" in name_upper
                      or "ACCESO OESTE" in name_upper):
                    financial_cost_ars += self.lg.cost_env.acceso_norte_oeste_ars
                elif ("BUENOS AIRES - LA PLATA" in name_upper
                      or "BUENOS AIRES-LA PLATA" in name_upper
                      or "RICCHERI" in name_upper):
                    financial_cost_ars += self.lg.cost_env.aubasa_sur_ars
                else:
                    financial_cost_ars += self.lg.cost_env.peaje_promedio_ars

            franquicia_ars = self.lg.cost_env.franquicia_seguro_usd * self.lg.cost_env.dolar_mep_ars
            route_fraction = dist_km / self.lg.ruta_tipica_km
            risk_cost_ars = p_failure * franquicia_ars * route_fraction
            
            w_expected_cost = financial_cost_ars + risk_cost_ars

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
        judge: 'BayesianJudge'
    ):
        self.rx_graph = rx_graph
        self.allowed_nodes = allowed_nodes
        self.cost_env = cost_env
        self.threat_matrix = threat_matrix
        self.ruta_tipica_km = ruta_tipica_km
        self.judge = judge
        
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


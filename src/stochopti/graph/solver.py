"""stochopti/graph/solver.py — Multi-Objective Solver Engine."""

import logging
import math
import time
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, FrozenSet, Any, Sequence

import numpy as np
import rustworkx as rx  # type: ignore

from stochopti.core.types import GraphSpec, EdgeSpec, PathSolution, ConstrainedSolution, canonical_route_key
from stochopti.core.protocols import EdgeCostFunction
from stochopti.core.exceptions import NodeNotFoundError, InfeasibleConstraintsError

LOGGER = logging.getLogger(__name__)

class VectorizedGraphIndex:
    """
    Mantiene la correspondencia biyectiva entre edge_index de rustworkx
    y las matrices de atributos contiguas en memoria.
    """
    def __init__(self, rx_graph: rx.PyDiGraph, edge_data_list: List[Tuple[int, int, EdgeSpec]], objective_keys: Tuple[str, ...]):
        self.objective_keys: Tuple[str, ...] = objective_keys
        self.k: int = len(objective_keys)
        
        # Max edge index is needed to allocate the dense array correctly
        edge_indices = rx_graph.edge_indices()
        self.num_edges: int = max(edge_indices) + 1 if edge_indices else 0
        
        # Matriz densa |max_edge_index| x K en memoria contigua (C-order)
        self.cost_matrix: np.ndarray = np.zeros((self.num_edges, self.k), dtype=np.float64)
        
        self.edge_id_to_index: Dict[str, int] = {}
        self.index_to_edge_id: List[str] = ["" for _ in range(self.num_edges)]
        self.index_to_edge_spec: Dict[int, EdgeSpec] = {}
        
        self._build_index(edge_data_list)

    def _build_index(self, edge_data_list: List[Tuple[int, int, EdgeSpec]]) -> None:
        for rx_u, rx_v, edge_spec in edge_data_list:
            # We assume edge_spec has the rx edge index stored in metadata for mapping
            idx = edge_spec.metadata.get("rx_index", -1)
            if idx < 0:
                continue
            self.edge_id_to_index[edge_spec.edge_id] = idx
            self.index_to_edge_id[idx] = edge_spec.edge_id
            self.index_to_edge_spec[idx] = edge_spec
            
            for k_idx, key in enumerate(self.objective_keys):
                self.cost_matrix[idx, k_idx] = edge_spec.objectives.get(key, 0.0)

    def compute_scalarized_weights(self, weights_vector: np.ndarray) -> np.ndarray:
        """
        Calcula w_e = sum_k (lambda_k * c_{e,k}) en una sola operación BLAS (O(|E|)).
        Retorna un arreglo 1D contiguo float64.
        """
        return np.dot(self.cost_matrix, weights_vector)

class EpsilonConstraintSolver:
    """
    Motor de búsqueda multi-objetivo implementando Epsilon-Constraint 
    y LARAC subgradient optimization.
    """
    def __init__(self, index: VectorizedGraphIndex, max_rcsp_iterations: int = 50, rtol: float = 1e-5, atol: float = 1e-8):
        self.index = index
        self.max_iter = max_rcsp_iterations
        self.rtol = rtol
        self.atol = atol
        self.last_audit: Dict[str, Any] = {}

    def solve_grid(
        self,
        graph: rx.PyDiGraph,
        source: int,
        target: int,
        epsilon_grid: np.ndarray
    ) -> List[ConstrainedSolution]:
        
        t0 = time.time()
        frontier: List[ConstrainedSolution] = []
        seen_paths: set = set()

        for epsilons in epsilon_grid:
            sol = self._solve_single_rcsp(graph, source, target, epsilons)
            if sol and sol.path_edges not in seen_paths:
                seen_paths.add(sol.path_edges)
                frontier.append(sol)
        
        filtered = self._filter_dominated(frontier)
        
        self.last_audit = {
            "source": source,
            "target": target,
            "solutions": len(filtered),
            "elapsed_ms": (time.time() - t0) * 1000,
            "timestamp": time.time(),
        }
        
        return filtered

    def _solve_single_rcsp(
        self, graph: rx.PyDiGraph, source: int, target: int, epsilons: np.ndarray
    ) -> Optional[ConstrainedSolution]:
        
        k_dims = self.index.k
        # Initialize multipliers for k-1 secondary objectives (zeros)
        mu = np.zeros(k_dims - 1, dtype=np.float64)
        
        best_sol: Optional[ConstrainedSolution] = None
        theta_0 = 1.0 # Initial step size
        
        for k_iter in range(1, self.max_iter + 1):
            # weight = obj_0 + sum(mu_j * obj_j)
            weights_vector = np.zeros(k_dims, dtype=np.float64)
            weights_vector[0] = 1.0
            weights_vector[1:] = mu
            
            edge_weights = self.index.compute_scalarized_weights(weights_vector)
            
            paths = rx.dijkstra_shortest_paths(
                graph,
                source=source,
                target=target,
                weight_fn=lambda e_spec: edge_weights[e_spec.metadata["rx_index"]],
                default_weight=1.0
            )
            
            if target not in paths:
                break # No path exists at all
                
            path_indices = paths[target]
            
            # Recuperar costo del camino usando suma compensada de Neumaier
            # para preservar la precisión de bits en objetivos con magnitudes dispares.
            path_edges_seq = []
            obj_sums = np.zeros(k_dims, dtype=np.float64)
            # Vector de compensación de error acumulado (algoritmo de Neumaier-Babuška)
            obj_comp = np.zeros(k_dims, dtype=np.float64)
            
            for i in range(len(path_indices) - 1):
                u = path_indices[i]
                v = path_indices[i+1]
                edges_uv = graph.edge_indices_from_endpoints(u, v)
                best_e_idx = -1
                best_e_w = math.inf
                for e_idx in edges_uv:
                    w = edge_weights[e_idx]
                    if w < best_e_w:
                        best_e_w = w
                        best_e_idx = e_idx
                        
                if best_e_idx != -1:
                    path_edges_seq.append(self.index.index_to_edge_id[best_e_idx])
                    # Neumaier compensated summation: obj_sums += cost_row
                    cost_row: np.ndarray = self.index.cost_matrix[best_e_idx]
                    new_sums: np.ndarray = obj_sums + cost_row
                    # Rama magnitud grande: error en cost_row; rama magnitud pequeña: error en obj_sums
                    larger = np.where(np.abs(obj_sums) >= np.abs(cost_row), obj_sums, cost_row)
                    smaller = np.where(np.abs(obj_sums) >= np.abs(cost_row), cost_row, obj_sums)
                    obj_comp += (larger - new_sums) + smaller
                    obj_sums = new_sums
            
            # Aplicar corrección acumulada de Neumaier al resultado final
            obj_sums = obj_sums + obj_comp
            
            sol = ConstrainedSolution(
                path_edges=canonical_route_key(path_edges_seq),
                objective_values=tuple(obj_sums)
            )
            
            # Check feasibility
            is_feasible = True
            for j in range(k_dims - 1):
                if obj_sums[j+1] > epsilons[j]:
                    is_feasible = False
                    break
                    
            if is_feasible:
                # If feasible, we found a candidate. Is it the best?
                if best_sol is None or sol.objective_values[0] < best_sol.objective_values[0]:
                    best_sol = sol
            
            # Update multipliers (subgradient step)
            theta_k = theta_0 / math.sqrt(k_iter)
            for j in range(k_dims - 1):
                mu[j] = max(0.0, mu[j] + theta_k * (obj_sums[j+1] - epsilons[j]))
                
        return best_sol

    def _filter_dominated(self, frontier: List[ConstrainedSolution]) -> List[ConstrainedSolution]:
        # Basic non-dominated sorting
        non_dominated = []
        for i, sol_i in enumerate(frontier):
            dominated = False
            for j, sol_j in enumerate(frontier):
                if i == j:
                    continue
                # sol_j dominates sol_i if it is <= in all objectives and < in at least one
                better_or_eq = True
                strictly_better = False
                
                for k in range(self.index.k):
                    val_j = sol_j.objective_values[k]
                    val_i = sol_i.objective_values[k]
                    
                    is_close = math.isclose(val_j, val_i, rel_tol=self.rtol, abs_tol=self.atol)
                    if not (val_j < val_i or is_close):
                        better_or_eq = False
                        break
                    if val_j < val_i and not is_close:
                        strictly_better = True
                        
                if better_or_eq and strictly_better:
                    dominated = True
                    break
            if not dominated:
                non_dominated.append(sol_i)
        return non_dominated


@dataclass(order=False)
class Label:
    """Etiqueta que representa un camino solución para la reconstrucción."""
    node_id: str
    objective_values: Dict[str, float]
    parent_label: Optional["Label"]
    edge_id_from_parent: Optional[str]
    seq: int = 0
    
    def __lt__(self, other: "Label") -> bool:
        s_self = sum(self.objective_values.values())
        s_other = sum(other.objective_values.values())
        if s_self != s_other:
            return s_self < s_other
        return self.seq < other.seq


class MultiObjectiveSolver:
    """
    [DEPRECATED] Wrapper transitorio hacia EpsilonConstraintSolver.
    """
    def __init__(
        self,
        cost_fn: EdgeCostFunction,
        n_passes: int = 10
    ) -> None:
        warnings.warn(
            "MultiObjectiveSolver is deprecated. Use EpsilonConstraintSolver natively.",
            DeprecationWarning,
            stacklevel=2
        )
        self.cost_fn = cost_fn
        self.n_passes = n_passes
        self.last_audit: Dict[str, Any] = {}
        # Cache for path reconstruction in deprecated mode
        self._edge_map: Dict[str, EdgeSpec] = {}
        self._label_solutions: Dict[int, ConstrainedSolution] = {}
        self._source: str = ""

    def solve(self, graph: GraphSpec, source: str, target: str) -> List[Label]:
        node_ids = {n.node_id for n in graph.nodes}
        if source not in node_ids:
            raise NodeNotFoundError(f"Source node {source} not found.")
        if target not in node_ids:
            raise NodeNotFoundError(f"Target node {target} not found.")

        self._source = source
        # Build edge lookup for path reconstruction
        self._edge_map = {e.edge_id: e for e in graph.edges}

        rx_graph = rx.PyDiGraph()
        str_to_rx: Dict[str, int] = {}
        rx_to_str: Dict[int, str] = {}
        
        for node in graph.nodes:
            idx = rx_graph.add_node(node.node_id)
            str_to_rx[node.node_id] = idx
            rx_to_str[idx] = node.node_id
            
        edge_data_list = []
        for edge in graph.edges:
            if edge.source not in str_to_rx or edge.target not in str_to_rx:
                continue
            u_rx = str_to_rx[edge.source]
            v_rx = str_to_rx[edge.target]
            rx_idx = rx_graph.add_edge(u_rx, v_rx, edge)
            edge.metadata["rx_index"] = rx_idx
            edge_data_list.append((u_rx, v_rx, edge))
            
        src_rx = str_to_rx.get(source)
        tgt_rx = str_to_rx.get(target)

        if src_rx is None or tgt_rx is None:
            return []

        obj_keys = graph.objective_names[:2] if len(graph.objective_names) >= 2 else ("obj1", "obj2")
        
        index = VectorizedGraphIndex(rx_graph, edge_data_list, obj_keys)
        new_solver = EpsilonConstraintSolver(index, max_rcsp_iterations=20)
        
        epsilons = []
        max_obj2 = 0.0
        for edge in graph.edges:
            max_obj2 += edge.objectives.get(obj_keys[1], 0.0)
            
        for i in range(self.n_passes):
            epsilons.append([max_obj2 * (1.0 - (i / max(1, self.n_passes - 1)))])
            
        epsilon_grid = np.array(epsilons, dtype=np.float64)
        
        solutions = new_solver.solve_grid(rx_graph, src_rx, tgt_rx, epsilon_grid)
        self.last_audit = new_solver.last_audit
        
        labels = []
        self._label_solutions = {}
        for i, sol in enumerate(solutions):
            curr_label = Label(
                node_id=target,
                objective_values={
                    obj_keys[0]: sol.objective_values[0],
                    obj_keys[1]: sol.objective_values[1] if len(sol.objective_values) > 1 else 0.0
                },
                parent_label=None,
                edge_id_from_parent=None,
                seq=i
            )
            self._label_solutions[i] = sol
            labels.append(curr_label)
            
        return labels

    def reconstruct_path(self, label: Label) -> PathSolution:
        """Reconstruct node path from the cached ConstrainedSolution edge sequence."""
        sol = self._label_solutions.get(label.seq)
        if sol is None or not sol.path_edges:
            return PathSolution(path=[], edges=[], objective_values=label.objective_values)
        
        edge_ids = list(sol.path_edges)
        nodes = [self._source]
        for eid in edge_ids:
            edge_spec = self._edge_map.get(eid)
            if edge_spec:
                nodes.append(edge_spec.target)
        
        return PathSolution(path=nodes, edges=edge_ids, objective_values=label.objective_values)

# src/bloque4/multiobjective_engine.py
"""
Dual-pass Dijkstra engine using rustworkx native compiled shortest-path.
Pass 1: minimize w_survival (safest route = "Tank")
Pass 2: minimize w_expected_cost (cheapest route = "Gambler")
The Pareto frontier is constructed from these two extremes plus interpolated solutions.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import rustworkx as rx

from .schema import Graph, Edge, RawSolution

LOGGER = logging.getLogger(__name__)


@dataclass(order=False)
class Label:
    """Label representing a complete path solution for Pareto extraction."""
    node_id: str
    w_survival: float
    w_expected_cost: float
    parent_label: Optional["Label"]
    edge_id_from_parent: Optional[str]
    seq: int = 0
    cum_cost: float = 0.0
    cum_time: float = 0.0
    cum_risk_weight: float = 0.0
    f_priority: float = 0.0

    def __lt__(self, other: "Label") -> bool:
        if self.w_survival != other.w_survival:
            return self.w_survival < other.w_survival
        if self.w_expected_cost != other.w_expected_cost:
            return self.w_expected_cost < other.w_expected_cost
        return self.seq < other.seq


class MultiObjectiveEngine:
    """
    High-performance dual-pass Dijkstra engine using rustworkx's native compiled
    shortest path algorithm. Finds Pareto-optimal solutions by optimizing each
    objective independently and then constructing the frontier.
    
    This replaces the pure-Python label-setting algorithm which couldn't traverse
    deep graphs (100+ hops) within practical iteration limits.
    """

    def __init__(
        self,
        eps_1: float = 0.1,
        eps_2: float = 50.0,
        max_labels_per_node: int = 1000,
        max_total_labels: int = 150000,
        max_iterations: int = 10_000_000,
    ) -> None:
        self.eps_1 = float(eps_1)
        self.eps_2 = float(eps_2)
        self.last_audit: dict = {}

    def solve(
        self,
        graph: Graph,
        source: str,
        target: str,
        node_coords: Optional[Dict[str, Tuple[float, float]]] = None,
    ) -> List[Label]:
        """
        Returns Pareto-optimal Labels at the target node using native Dijkstra.
        
        Strategy:
        1. Build a temporary rustworkx DiGraph from the legacy Graph edges
        2. Run Dijkstra minimizing w_survival → "Tank" route
        3. Run Dijkstra minimizing w_expected_cost → "Gambler" route
        4. Run Dijkstra minimizing balanced (w_survival + w_expected_cost) → "Balancer"
        5. Return all unique solutions as Labels
        """
        t0 = time.time()
        
        # Validate terminals
        node_ids = {n.node_id for n in graph.nodes}
        if source not in node_ids:
            raise ValueError(f"Source node {source} not found in graph.")
        if target not in node_ids:
            raise ValueError(f"Target node {target} not found in graph.")

        # Build temporary rustworkx graph with string node IDs mapped to integers
        rx_graph = rx.PyDiGraph()
        str_to_rx: Dict[str, int] = {}
        
        for node in graph.nodes:
            idx = rx_graph.add_node(node.node_id)
            str_to_rx[node.node_id] = idx
        
        # Store edge data for path reconstruction
        edge_data: Dict[Tuple[int, int, int], Edge] = {}  # (u_rx, v_rx, edge_idx) -> Edge
        
        for edge in graph.edges:
            if edge.source not in str_to_rx or edge.target not in str_to_rx:
                continue
            u_rx = str_to_rx[edge.source]
            v_rx = str_to_rx[edge.target]
            edge_idx = rx_graph.add_edge(u_rx, v_rx, edge)
            edge_data[(u_rx, v_rx, edge_idx)] = edge

        src_rx = str_to_rx.get(source)
        tgt_rx = str_to_rx.get(target)
        
        if src_rx is None or tgt_rx is None:
            LOGGER.error("Source or target not mapped to rustworkx indices")
            return []

        LOGGER.info("Built temporary rx graph: %d nodes, %d edges", rx_graph.num_nodes(), rx_graph.num_edges())

        labels: List[Label] = []
        seq = 0
        
        # Build adjacency for edge lookup
        edge_by_source: Dict[str, List[Edge]] = {}
        for e in graph.edges:
            edge_by_source.setdefault(e.source, []).append(e)

        def _build_label_from_path(node_path: List[int], label_seq: int) -> Optional[Label]:
            """Reconstruct a Label chain from a rustworkx node path."""
            if not node_path:
                return None
            
            nonlocal seq
            
            # Convert rx indices back to string node IDs
            str_path = [rx_graph[idx] for idx in node_path]
            
            # Build the label chain
            current_label = Label(
                node_id=str_path[0],
                w_survival=0.0,
                w_expected_cost=0.0,
                parent_label=None,
                edge_id_from_parent=None,
                seq=label_seq,
            )
            
            for i in range(len(str_path) - 1):
                src_id = str_path[i]
                tgt_id = str_path[i + 1]
                
                # Find the edge between these nodes
                best_edge = None
                for e in edge_by_source.get(src_id, []):
                    if e.target == tgt_id:
                        if best_edge is None or e.w_expected_cost < best_edge.w_expected_cost:
                            best_edge = e
                
                if best_edge is None:
                    LOGGER.warning("No edge found between %s and %s in path reconstruction", src_id, tgt_id)
                    return None
                
                seq += 1
                new_label = Label(
                    node_id=tgt_id,
                    w_survival=current_label.w_survival + best_edge.w_survival,
                    w_expected_cost=current_label.w_expected_cost + best_edge.w_expected_cost,
                    parent_label=current_label,
                    edge_id_from_parent=best_edge.edge_id,
                    seq=seq,
                )
                new_label.cum_cost = current_label.cum_cost + float(best_edge.cost or 0.0)
                new_label.cum_time = current_label.cum_time + float(getattr(best_edge, 'time', 0.0) or 0.0)
                new_label.cum_risk_weight = current_label.cum_risk_weight + float(getattr(best_edge, 'risk_weight', 0.0) or 0.0)
                current_label = new_label
            
            return current_label

        # ===== MUESTREO DE PARETO POR ESCALARIZACIÓN (10 pases) =====
        seen_routes: set = set()   # frozenset(edge_ids) para deduplicación
        n_passes = 10
        
        for i in range(n_passes):
            lmbda = i / (n_passes - 1)   # 0.0, 0.111, ..., 1.0
            
            try:
                paths = rx.dijkstra_shortest_paths(
                    rx_graph, src_rx, tgt_rx,
                    weight_fn=lambda e, _l=lmbda: _l * e.w_survival + (1 - _l) * (e.w_expected_cost / 1000.0)
                )
                
                if tgt_rx not in paths:
                    continue
                
                seq += 1
                label = _build_label_from_path(paths[tgt_rx], seq)
                if label is None:
                    continue
                
                # Deduplicación por composición exacta de aristas
                route_edges = []
                cursor = label
                while cursor is not None:
                    if cursor.edge_id_from_parent is not None:
                        route_edges.append(cursor.edge_id_from_parent)
                    cursor = cursor.parent_label
                route_key = frozenset(route_edges)
                
                if route_key in seen_routes:
                    continue
                seen_routes.add(route_key)
                
                labels.append(label)
                LOGGER.info(
                    "PASS %d (λ=%.2f): w_surv=%.4f, w_cost=%.2f, hops=%d",
                    i + 1, lmbda, label.w_survival, label.w_expected_cost, len(paths[tgt_rx])
                )
            except Exception as e:
                LOGGER.exception("Dijkstra pass %d (λ=%.2f) failed: %s", i + 1, lmbda, e)

        elapsed_ms = (time.time() - t0) * 1000

        LOGGER.info(
            "MOEngine λ-scalarization summary: src=%s tgt=%s passes=%d unique_routes=%d elapsed=%.1fms",
            source, target, n_passes, len(labels), elapsed_ms
        )

        self.last_audit = {
            "source": source,
            "target": target,
            "eps_1": self.eps_1,
            "eps_2": self.eps_2,
            "solutions": len(labels),
            "elapsed_ms": elapsed_ms,
            "timestamp": time.time(),
        }

        return labels

    def reconstruct_path(self, label: Label) -> RawSolution:
        """Reconstructs an exact RawSolution from a final label."""
        edges: List[str] = []
        nodes: List[str] = []
        current = label
        while current is not None:
            nodes.append(current.node_id)
            if current.edge_id_from_parent is not None:
                edges.append(current.edge_id_from_parent)
            current = current.parent_label
        nodes.reverse()
        edges.reverse()
        return RawSolution(
            path=nodes,
            edges=edges,
            total_cost=label.cum_cost,
            optimized_cost=label.w_expected_cost,
            total_time=label.cum_time,
            total_risk=label.cum_risk_weight,
        )

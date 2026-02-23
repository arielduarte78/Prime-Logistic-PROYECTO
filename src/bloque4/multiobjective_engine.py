# src/bloque4/multiobjective_engine.py
from __future__ import annotations

import heapq
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .schema import Graph, Edge, RawSolution

LOGGER = logging.getLogger(__name__)


@dataclass(order=False)
class Label:
    """Label for multi‑objective label‑setting algorithm."""
    node_id: str
    w_survival: float          # cumulative survival weight = sum(-ln(1-P(F)))
    w_expected_cost: float      # cumulative expected cost = sum(cost + P(F)*impact)
    parent_label: Optional["Label"]
    edge_id_from_parent: Optional[str]
    seq: int = 0                # tie-breaker sequence number, assigned by the engine
    # Exact accumulators for precise reconstruction
    cum_cost: float = 0.0
    cum_time: float = 0.0
    cum_risk_weight: float = 0.0

    def __lt__(self, other: "Label") -> bool:
        """
        Lexicographic ordering:
        1. smaller w_survival (higher survival probability) first,
        2. then smaller w_expected_cost,
        3. then sequence number (to avoid ambiguity).
        """
        if self.w_survival != other.w_survival:
            return self.w_survival < other.w_survival
        if self.w_expected_cost != other.w_expected_cost:
            return self.w_expected_cost < other.w_expected_cost
        return self.seq < other.seq


class MultiObjectiveEngine:
    """
    ε‑approximate label‑setting algorithm for two objectives:
        - minimize w_survival (→ maximize survival probability)
        - minimize w_expected_cost

    Dominance is checked via a discrete grid per node:
        box_1 = floor(w_survival / eps_1)
        box_2 = floor(w_expected_cost / eps_2)

    Only labels in the same box are compared for ε‑dominance; adjacent boxes are not checked.
    This yields an ε‑approximate Pareto set.

    `active_labels_per_node` counts the number of boxes currently occupied (one label per box).
    `labels_per_node` stores a bounded historical list of labels for debugging and reconstruction;
    it is truncated to avoid unbounded growth.
    """

    def __init__(
        self,
        eps_1: float = 0.001,
        eps_2: float = 1.0,
        max_labels_per_node: int = 1000,
        max_total_labels: int = 100000,
        max_iterations: int = 10_000_000
    ) -> None:
        if eps_1 <= 0.0 or eps_2 <= 0.0:
            raise ValueError("eps_1 and eps_2 must be positive.")
        self.eps_1 = eps_1
        self.eps_2 = eps_2
        self.max_labels_per_node = int(max_labels_per_node)
        self.max_total_labels = int(max_total_labels)
        self.max_iterations = int(max_iterations)
        self.last_audit: dict = {}  # to be filled after solve()

    def solve(self, graph: Graph, source: str, target: str) -> List[Label]:
        """
        Returns the Pareto‑ε‑approximate frontier at the target node.
        """
        # Validate terminals
        node_ids = {n.node_id for n in graph.nodes}
        if source not in node_ids:
            raise ValueError(f"Source node {source} not found in graph.")
        if target not in node_ids:
            raise ValueError(f"Target node {target} not found in graph.")

        # Validate that all edges have preprocessed weights
        for e in graph.edges:
            ws = getattr(e, "w_survival", None)
            we = getattr(e, "w_expected_cost", None)
            if ws is None or we is None:
                raise ValueError(f"Edge {e.edge_id} missing w_survival or w_expected_cost; run weight_builder first.")
            if not (isinstance(ws, (int, float)) and isinstance(we, (int, float))):
                raise ValueError(f"Edge {e.edge_id} has non-numeric weights: w_survival={ws!r}, w_expected_cost={we!r}")
            if math.isnan(ws) or math.isnan(we) or math.isinf(ws) or math.isinf(we):
                raise ValueError(f"Edge {e.edge_id} has invalid numeric weights: w_survival={ws}, w_expected_cost={we}")
            if ws < 0 or we < 0:
                raise ValueError(f"Edge {e.edge_id} has negative weights: w_survival={ws}, w_expected_cost={we}")

        # Data structures
        labels_per_node: Dict[str, List[Label]] = {node.node_id: [] for node in graph.nodes}
        # grid_per_node[node][(box1,box2)] = best label in that box (lowest w_expected_cost)
        grid_per_node: Dict[str, Dict[Tuple[int, int], Label]] = {node.node_id: {} for node in graph.nodes}
        # active_labels_per_node counts the number of labels currently stored in the grid (one per box)
        active_labels_per_node: Dict[str, int] = {node.node_id: 0 for node in graph.nodes}
        total_labels_generated = 0      # labels that entered the grid (new best in a box)
        total_labels_pushed = 0          # labels pushed onto the heap (including those later pruned)
        total_labels_pruned = 0

        # Priority queue (min‑heap) ordered by __lt__
        heap: List[Label] = []

        # Build quick outgoing edge map for efficiency
        outgoing: Dict[str, List[Edge]] = {}
        for edge in graph.edges:
            outgoing.setdefault(edge.source, []).append(edge)

        # Initial label at source
        seq = 0
        start_label = Label(
            node_id=source,
            w_survival=0.0,
            w_expected_cost=0.0,
            parent_label=None,
            edge_id_from_parent=None,
            seq=seq,
        )
        heapq.heappush(heap, start_label)
        total_labels_pushed += 1
        # register start label in grid and labels_per_node
        start_box = (int(0.0 // self.eps_1), int(0.0 // self.eps_2))
        grid_per_node[source][start_box] = start_label
        labels_per_node[source].append(start_label)
        active_labels_per_node[source] += 1
        total_labels_generated += 1

        iterations = 0
        while heap:
            iterations += 1
            if iterations > self.max_iterations or total_labels_generated > self.max_total_labels:
                # Safety truncation
                LOGGER.warning(
                    "MOEngine safety limit reached: iterations=%d, generated=%d",
                    iterations, total_labels_generated
                )
                break

            label = heapq.heappop(heap)

            # 1. Grid‑based dominance check: if a label in the same box has lower w_expected_cost,
            #    and the difference is at least eps_2, the current label is ε‑dominated.
            box = (
                int(label.w_survival // self.eps_1),
                int(label.w_expected_cost // self.eps_2),
            )
            best_in_box = grid_per_node[label.node_id].get(box)
            # If the stored label is a different instance and is at least eps_2 better, skip this popped label.
            if best_in_box is not None and best_in_box is not label and best_in_box.w_expected_cost <= label.w_expected_cost - self.eps_2:
                LOGGER.debug("Pruned by grid (same box): label %s (w_surv=%.4f, w_exp=%.4f) vs best (w_exp=%.4f)",
                             label.seq, label.w_survival, label.w_expected_cost, best_in_box.w_expected_cost)
                total_labels_pruned += 1
                continue

            # 2. Store/update the label in the node's structures
            #    (only if it is not ε‑dominated by the existing best in its box)
            existing = grid_per_node[label.node_id].get(box)
            if existing is None or label.w_expected_cost < existing.w_expected_cost:
                # If we are replacing an existing label, decrement the active count for that node
                if existing is not None:
                    LOGGER.debug("Replacing label %s in box %s with label %s (better w_exp)", existing.seq, box, label.seq)
                    active_labels_per_node[label.node_id] -= 1
                # New label becomes the best in this box
                grid_per_node[label.node_id][box] = label
                # Keep a bounded historical list for debugging (truncate if too long)
                labels_per_node[label.node_id].append(label)
                if len(labels_per_node[label.node_id]) > 10 * self.max_labels_per_node:
                    # keep only recent ones
                    labels_per_node[label.node_id] = labels_per_node[label.node_id][-self.max_labels_per_node:]
                active_labels_per_node[label.node_id] += 1
                total_labels_generated += 1

                # Optional: remove labels from other boxes that are now strictly dominated
                # (full Pareto dominance is costly; we rely on ε‑grid to keep approximation)

            # 3. Expansion
            for edge in outgoing.get(label.node_id, []):
                if edge.target is None:  # safety
                    continue
                seq += 1
                new_label = Label(
                    node_id=edge.target,
                    w_survival=label.w_survival + edge.w_survival,
                    w_expected_cost=label.w_expected_cost + edge.w_expected_cost,
                    parent_label=label,
                    edge_id_from_parent=edge.edge_id,
                    seq=seq,
                )
                # propagate exact accumulators
                _cost = getattr(edge, "cost", 0.0) or 0.0
                _time = getattr(edge, "time", 0.0) or 0.0
                _risk_w = getattr(edge, "risk_weight", 0.0) or 0.0

                new_label.cum_cost = label.cum_cost + float(_cost)
                new_label.cum_time = label.cum_time + float(_time)
                new_label.cum_risk_weight = label.cum_risk_weight + float(_risk_w)


                # Quick prune using the grid of the target node
                target_box = (
                    int(new_label.w_survival // self.eps_1),
                    int(new_label.w_expected_cost // self.eps_2),
                )
                best_in_target = grid_per_node[edge.target].get(target_box)
                if best_in_target is not None and best_in_target.w_expected_cost <= new_label.w_expected_cost - self.eps_2:
                    LOGGER.debug("Pruned new label to %s (box %s) by target grid: best w_exp=%.4f, new w_exp=%.4f",
                                 edge.target, target_box, best_in_target.w_expected_cost, new_label.w_expected_cost)
                    total_labels_pruned += 1
                    continue

                # safety: avoid exploding labels per node
                if active_labels_per_node[edge.target] >= self.max_labels_per_node:
                    LOGGER.debug("Pruned new label to %s due to active label limit (%d)", edge.target, self.max_labels_per_node)
                    total_labels_pruned += 1
                    continue

                heapq.heappush(heap, new_label)
                total_labels_pushed += 1
                LOGGER.debug("Pushed label %s to heap for node %s (box %s)", seq, edge.target, target_box)

        # Logging summary for audit
        LOGGER.info(
            "MOEngine summary src=%s tgt=%s eps1=%s eps2=%s generated=%d pushed=%d pruned=%d iterations=%d",
            source, target, self.eps_1, self.eps_2, total_labels_generated, total_labels_pushed, total_labels_pruned, iterations
        )

        # Expose audit for caller to persist
        self.last_audit = {
            "source": source,
            "target": target,
            "eps_1": self.eps_1,
            "eps_2": self.eps_2,
            "generated": int(total_labels_generated),
            "pushed": int(total_labels_pushed),
            "pruned": int(total_labels_pruned),
            "iterations": int(iterations),
            "max_labels_per_node": int(self.max_labels_per_node),
            "timestamp": __import__("time").time(),
        }

        # Return the frontier at the target
        return labels_per_node.get(target, [])

    def reconstruct_path(self, label: Label) -> RawSolution:
        """
        Reconstructs an exact RawSolution from a final label using the stored accumulators.
        Note: `optimized_cost` is returned as the label.w_expected_cost (expected-cost axis).
        """
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
            optimized_cost=label.w_expected_cost,  # scalarized value along expected‑cost axis
            total_time=label.cum_time,
            total_risk=label.cum_risk_weight
        )
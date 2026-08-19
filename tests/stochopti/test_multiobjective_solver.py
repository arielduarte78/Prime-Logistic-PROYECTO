"""Tests for MultiObjectiveSolver — dual-pass Dijkstra on rustworkx."""
import pytest
from stochopti.graph.solver import MultiObjectiveSolver
from stochopti.core.exceptions import NodeNotFoundError
from stochopti.core.types import GraphSpec, NodeSpec, EdgeSpec


class SimpleCostFn:
    """Trivial linear scalarization for testing."""
    def __call__(self, edge: EdgeSpec, weights: dict) -> float:
        return sum(
            weights.get(k, 1.0) * edge.objectives.get(k, 0.0)
            for k in edge.objectives
        )


def _make_diamond_graph() -> GraphSpec:
    """
    A → B → D  (cheap but risky)
    A → C → D  (expensive but safe)
    """
    return GraphSpec(
        nodes=[NodeSpec("A"), NodeSpec("B"), NodeSpec("C"), NodeSpec("D")],
        edges=[
            EdgeSpec("e_ab", "A", "B", {"cost": 1.0, "risk": 0.9}),
            EdgeSpec("e_bd", "B", "D", {"cost": 1.0, "risk": 0.9}),
            EdgeSpec("e_ac", "A", "C", {"cost": 10.0, "risk": 0.01}),
            EdgeSpec("e_cd", "C", "D", {"cost": 10.0, "risk": 0.01}),
        ],
        objective_names=("cost", "risk"),
    )


def test_solver_finds_solutions():
    graph = _make_diamond_graph()
    solver = MultiObjectiveSolver(cost_fn=SimpleCostFn(), n_passes=10)

    labels = solver.solve(graph, source="A", target="D")

    assert len(labels) >= 1
    # Extract paths for comparison
    paths = []
    for lbl in labels:
        sol = solver.reconstruct_path(lbl)
        paths.append(sol.path)

    # At least the cheap path should always appear
    assert ["A", "B", "D"] in paths


def test_solver_finds_both_pareto_optimal():
    """With enough passes, both the cheap-risky and expensive-safe paths should appear."""
    graph = _make_diamond_graph()
    solver = MultiObjectiveSolver(cost_fn=SimpleCostFn(), n_passes=20)

    labels = solver.solve(graph, source="A", target="D")
    paths = [solver.reconstruct_path(lbl).path for lbl in labels]

    assert ["A", "B", "D"] in paths
    assert ["A", "C", "D"] in paths


def test_solver_reconstruct_objectives():
    graph = _make_diamond_graph()
    solver = MultiObjectiveSolver(cost_fn=SimpleCostFn(), n_passes=10)

    labels = solver.solve(graph, source="A", target="D")
    assert len(labels) > 0

    sol = solver.reconstruct_path(labels[0])
    assert "cost" in sol.objective_values
    assert "risk" in sol.objective_values


def test_solver_unreachable_target():
    graph = GraphSpec(
        nodes=[NodeSpec("A"), NodeSpec("B"), NodeSpec("C")],
        edges=[EdgeSpec("e1", "A", "B", {"cost": 1.0, "risk": 0.1})],
        objective_names=("cost", "risk"),
    )
    solver = MultiObjectiveSolver(cost_fn=SimpleCostFn())
    labels = solver.solve(graph, source="A", target="C")
    assert labels == []


def test_solver_invalid_source():
    graph = GraphSpec(
        nodes=[NodeSpec("A")],
        edges=[],
        objective_names=("cost", "risk"),
    )
    solver = MultiObjectiveSolver(cost_fn=SimpleCostFn())
    with pytest.raises(NodeNotFoundError, match="Source node"):
        solver.solve(graph, source="X", target="A")

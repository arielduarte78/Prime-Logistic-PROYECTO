"""Tests for ParetoFrontier and scoring pipeline."""
import pytest
from stochopti.pareto.frontier import ParetoFrontier, ParetoSolution
from stochopti.pareto.scoring import build_scored_options


def _make_frontier() -> ParetoFrontier:
    return ParetoFrontier(solutions=[
        ParetoSolution(
            path=("A", "B", "C"), edges=("e1", "e2"),
            objective_values={"cost": 10.0, "risk": 0.5},
        ),
        ParetoSolution(
            path=("A", "C"), edges=("e3",),
            objective_values={"cost": 50.0, "risk": 0.01},
        ),
        ParetoSolution(
            path=("A", "D", "C"), edges=("e4", "e5"),
            objective_values={"cost": 60.0, "risk": 0.6},
        ),
    ])


def test_extract_min_objective_1():
    frontier = _make_frontier()
    best = frontier.extract_min_objective_1("cost")
    assert best is not None
    assert best.objective_values["cost"] == 10.0


def test_extract_min_objective_2():
    frontier = _make_frontier()
    best = frontier.extract_min_objective_2("risk")
    assert best is not None
    assert best.objective_values["risk"] == pytest.approx(0.01)


def test_extract_utopian_closest():
    frontier = _make_frontier()
    closest = frontier.extract_utopian_closest("cost", "risk")
    assert closest is not None
    # The utopian closest should be the one with best balance
    assert closest.path in [("A", "B", "C"), ("A", "C")]


def test_empty_frontier():
    frontier = ParetoFrontier()
    assert frontier.extract_min_objective_1("cost") is None
    assert frontier.extract_utopian_closest("cost", "risk") is None


def test_scored_options_pipeline():
    frontier = _make_frontier()
    scored = build_scored_options(frontier, "cost", "risk")

    assert len(scored) == 3
    for opt in scored:
        assert 0.0 <= opt.recommendation_strength <= 1.0
        assert len(opt.tags) > 0

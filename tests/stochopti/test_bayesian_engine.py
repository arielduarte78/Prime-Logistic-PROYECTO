"""Tests for BayesianRiskEngine — vectorized risk priors on graphs."""
import pytest
import numpy as np
from stochopti.bayesian.engine import BayesianRiskEngine
from stochopti.core.types import GraphSpec, NodeSpec, EdgeSpec, BetaPrior


def test_standalone_initialization():
    """Standalone mode: no graph, default priors."""
    engine = BayesianRiskEngine()
    assert not engine.integrity_compromised

    params = engine.system_params()
    assert params.alpha == 2.0
    assert params.beta == 2.0


def test_graph_with_prior_provider():
    """Graph mode with injected PriorProvider."""
    graph = GraphSpec(
        nodes=[NodeSpec("A"), NodeSpec("B")],
        edges=[EdgeSpec("e1", "A", "B", {"cost": 10.0})],
        objective_names=("cost",),
    )

    class MockPriorProvider:
        def get_priors(self):
            return {("A", "B"): BetaPrior(5.0, 1.0)}

    engine = BayesianRiskEngine(graph=graph, prior_provider=MockPriorProvider())
    params = engine.get_params("A", "B")

    assert params.alpha == pytest.approx(5.0)
    assert params.beta == pytest.approx(1.0)


def test_update_edge():
    graph = GraphSpec(
        nodes=[NodeSpec("A"), NodeSpec("B")],
        edges=[EdgeSpec("e1", "A", "B", {"cost": 10.0})],
        objective_names=("cost",),
    )

    engine = BayesianRiskEngine(graph=graph)
    engine.update_edge("A", "B", successes=3.0, failures=0.0)

    params = engine.get_params("A", "B")
    assert params.alpha == pytest.approx(5.0)  # default 2.0 + 3.0
    assert params.beta == pytest.approx(2.0)   # default 2.0


def test_get_params_missing_edge_returns_default():
    engine = BayesianRiskEngine()
    params = engine.get_params("X", "Y")
    assert params.alpha == 2.0
    assert params.beta == 2.0


def test_threat_provider_degrades_priors():
    """ThreatProvider should reduce alpha and increase beta."""
    graph = GraphSpec(
        nodes=[NodeSpec("A"), NodeSpec("B")],
        edges=[EdgeSpec("e1", "A", "B", {"cost": 10.0})],
        objective_names=("cost",),
    )

    class MockThreatProvider:
        def get_threat_level(self, edge):
            return 0.8  # high threat

    engine = BayesianRiskEngine(
        graph=graph,
        threat_provider=MockThreatProvider(),
        default_prior=BetaPrior(10.0, 10.0),
    )
    params = engine.get_params("A", "B")

    # alpha degraded: 10 * (1 - 0.8*0.5) = 10 * 0.6 = 6.0
    # beta degraded:  10 * (1 + 0.8*0.5) = 10 * 1.4 = 14.0
    assert params.alpha == pytest.approx(6.0)
    assert params.beta == pytest.approx(14.0)


def test_ephemeral_clone_independence():
    """Clone should not share mutable state with parent."""
    graph = GraphSpec(
        nodes=[NodeSpec("A"), NodeSpec("B")],
        edges=[EdgeSpec("e1", "A", "B", {"cost": 10.0})],
        objective_names=("cost",),
    )
    engine = BayesianRiskEngine(graph=graph, default_prior=BetaPrior(5.0, 5.0))
    clone = engine.spawn_ephemeral_clone()

    clone.update_edge("A", "B", successes=100.0, failures=0.0)

    parent_params = engine.get_params("A", "B")
    clone_params = clone.get_params("A", "B")

    assert parent_params.alpha == pytest.approx(5.0)
    assert clone_params.alpha == pytest.approx(105.0)


def test_emergency_mode_resets_priors():
    graph = GraphSpec(
        nodes=[NodeSpec("A"), NodeSpec("B")],
        edges=[EdgeSpec("e1", "A", "B", {"cost": 10.0})],
        objective_names=("cost",),
    )
    engine = BayesianRiskEngine(graph=graph, default_prior=BetaPrior(99.0, 1.0))
    engine.activate_emergency_mode()

    params = engine.get_params("A", "B")
    assert params.alpha == pytest.approx(1.0)
    assert params.beta == pytest.approx(1.0)

"""Tests for MonteCarloEngine — abstract stochastic simulation."""
import pytest
from stochopti.montecarlo.engine import MonteCarloEngine


class MockMutator:
    def apply_event(self, state, event):
        state["score"] += event
        return float(event)


class MockGenerator:
    def generate_events(self):
        return [1.0, 2.0]


class MockEvaluator:
    def evaluate(self, state):
        return {"total_score": state["score"]}


def _mock_state_factory():
    return {"score": 0.0}

def test_engine_runs_correct_iterations():
    engine = MonteCarloEngine(
        state_factory=_mock_state_factory,
        event_generator=MockGenerator(),
        mutator=MockMutator(),
        evaluator=MockEvaluator(),
    )
    results = engine.run(max_iter=10)
    assert len(results) == 10


def test_engine_accumulates_events():
    engine = MonteCarloEngine(
        state_factory=_mock_state_factory,
        event_generator=MockGenerator(),
        mutator=MockMutator(),
        evaluator=MockEvaluator(),
    )
    results = engine.run(max_iter=1)

    assert results[0]["metrics"]["total_score"] == pytest.approx(3.0)
    assert len(results[0]["events"]) == 2


def test_engine_state_isolation():
    """Each iteration gets a fresh state from the factory."""
    engine = MonteCarloEngine(
        state_factory=_mock_state_factory,
        event_generator=MockGenerator(),
        mutator=MockMutator(),
        evaluator=MockEvaluator(),
    )
    results = engine.run(max_iter=3)

    # Every iteration should produce the same score (fresh state each time)
    for r in results:
        assert r["metrics"]["total_score"] == pytest.approx(3.0)

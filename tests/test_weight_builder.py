# tests/test_weight_builder.py
from bloque4.weight_builder import build_edge_weights
from bloque4.schema import Edge

def test_build_edge_weights_basic():
    e = Edge(edge_id="e1", source="A", target="B", cost=100.0, distance=1.0, mode="truck")
    report = {"edges": {"e1": {"prob_failure": 0.10, "impact_mean": 50}}}
    build_edge_weights([e], report)
    assert hasattr(e, "w_survival")
    assert hasattr(e, "w_expected_cost")
    assert abs(e.w_survival - 0.10536051565782628) < 1e-9
    assert abs(e.w_expected_cost - 105.0) < 1e-9

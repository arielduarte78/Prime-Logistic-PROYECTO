#test for smoke test of weight builder

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from bloque4.schema import Edge
from bloque4.weight_builder import build_weights
import math

edges = [
    Edge(edge_id="A->B", source="A", target="B", cost=10.0, distance=1.0, mode="road"),
    Edge(edge_id="B->C", source="B", target="C", cost=5.0, distance=2.0, mode="road"),
]

report = {
    "edges": {
        "A->B": {"prob_failure": 0.1, "impact_mean": 20.0},
        "B->C": {"prob_failure": 0.0, "impact_mean": 0.0},
    },
    "nodes": {}
}

build_weights(edges, report)

print("A->B w_survival:", edges[0].w_survival, "expected ≈", -math.log(1 - 0.1))
print("A->B w_expected_cost:", edges[0].w_expected_cost, "expected =", 10.0 + 0.1 * 20.0)
print("B->C w_survival:", edges[1].w_survival, "expected = 0.0")
print("B->C w_expected_cost:", edges[1].w_expected_cost, "expected =", 5.0 + 0.0 * 0.0)

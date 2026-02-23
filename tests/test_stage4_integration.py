# tests/test_stage4_integration.py
from bloque4.multiobjective_engine import MultiObjectiveEngine
from bloque4.schema import Node, Edge, Graph, OptimizerConfig
from bloque4.pareto import ParetoFrontResult
from bloque4.report import build_strategic_options_from_frontier, PrimeStrategicReporter

def make_min_graph():
    nA = Node(node_id="A")
    nC = Node(node_id="C")
    e1 = Edge(
        edge_id="e1",
        source="A",
        target="C",
        cost=5.0,
        distance=1.0,
        mode="truck",
        time=0.0,
        w_survival=0.01,
        w_expected_cost=5.1
    )
    g = Graph(nodes=[nA, nC], edges=[e1], edge_indexer={"e1": 0})
    return g

def test_stage4_pipeline_smoke():
    g = make_min_graph()
    engine = MultiObjectiveEngine(eps_1=0.001, eps_2=0.1)
    frontier = engine.solve(g, source="A", target="C")

    # Pareto frontier must be non-empty for this graph
    assert isinstance(frontier, list)
    assert len(frontier) >= 1

    # Reconstruct and wrap
    pf = ParetoFrontResult.from_labels(frontier, engine)
    audit = pf.to_audit()
    assert audit["n_solutions"] >= 1
    assert audit["has_tank"] is True
    assert audit["has_gambler"] is True

    # Build strategic options and generate report
    config = OptimizerConfig(source_node_id="A", target_node_id="C")
    options = build_strategic_options_from_frontier(frontier, engine, config)
    assert isinstance(options, list)
    assert len(options) >= 1

    reporter = PrimeStrategicReporter(config=config)
    report = reporter.generate_full_report(options)
    assert isinstance(report, str)
    # Basic content checks
    assert "PRIME LOGISTICS INTELLIGENCE" in report or "CONCLUSIÓN FINAL" in report

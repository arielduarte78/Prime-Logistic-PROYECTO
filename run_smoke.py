from bloque4.multiobjective_engine import MultiObjectiveEngine
from bloque4.schema import Node, Edge, Graph, OptimizerConfig
from bloque4.pareto import ParetoFrontResult
from bloque4.report import build_strategic_options_from_frontier, PrimeStrategicReporter

# Grafo mínimo A->C directo
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

# Engine
engine = MultiObjectiveEngine(eps_1=0.001, eps_2=0.1)
frontier = engine.solve(g, source="A", target="C")

# Pareto audit + archetypes
pf = ParetoFrontResult.from_labels(frontier, engine)
print("Pareto audit:", pf.to_audit())
tank = pf.extract_tank()
print("Tank:", tank.to_dict() if tank else None)
gambler = pf.extract_gambler()
print("Gambler:", gambler.to_dict() if gambler else None)
tightrope = pf.extract_tightrope()
print("Tightrope:", tightrope.to_dict() if tightrope else None)
print("Unicorn:", pf.extract_unicorn() and pf.extract_unicorn().to_dict())

# Construir StrategicOption y generar reporte
config = OptimizerConfig(source_node_id="A", target_node_id="C")
options = build_strategic_options_from_frontier(frontier, engine, config)

reporter = PrimeStrategicReporter(config=config)
full_report = reporter.generate_full_report(options)

print("\n=== FULL STRATEGIC REPORT ===\n")
print(full_report)

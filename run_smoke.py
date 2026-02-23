from bloque4.multiobjective_engine import MultiObjectiveEngine
from bloque4.schema import Node, Edge, Graph

# Grafo mínimo A->C directo
nA = Node(node_id="A")
nC = Node(node_id="C")
e1 = Edge(edge_id="e1", source="A", target="C", cost=5.0, distance=1.0, mode="truck", w_survival=0.01, w_expected_cost=5.1)
g = Graph(nodes=[nA, nC], edges=[e1], edge_indexer={"e1": 0})

engine = MultiObjectiveEngine(eps_1=0.001, eps_2=0.1)
frontier = engine.solve(g, source="A", target="C")
print("Frontier size:", len(frontier))
if frontier:
    lbl = frontier[0]
    sol = engine.reconstruct_path(lbl)
    print("Path:", sol.path, "total_cost:", sol.total_cost)
print("Audit:", engine.last_audit)

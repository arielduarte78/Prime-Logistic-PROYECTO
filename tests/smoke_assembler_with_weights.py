# tests/smoke_assembler_with_weights.py
from bloque4.assembler import GraphAssembler

# Simulación mínima: indexer con _arcs y get_node
class DummyArc:
    def __init__(self, origin, destination, mode=None, distance=0.0, metadata=None):
        self.origin = origin
        self.destination = destination
        self.mode = mode
        self.distance = distance
        self.metadata = metadata
        self.cost_profile = None

class DummyIndexer:
    def __init__(self):
        self._arcs = {
            "A->B": DummyArc("A", "B"),
            "B->C": DummyArc("B", "C"),
        }
        self._nodes = {
            "A": type("N", (), {"lat": -34.6, "lon": -58.4}),
            "B": type("N", (), {"lat": -34.7, "lon": -58.5}),
            "C": type("N", (), {"lat": -34.8, "lon": -58.6}),
        }
    def get_node(self, nid):
        return self._nodes.get(nid)

def main():
    indexer = DummyIndexer()
    node_ids = ["A", "B", "C"]
    fragility_map = {"B": 0.1, "C": 0.0}

    # Simular reliability_report con entradas para arcos
    report = {
        "edges": {
            "A->B": {"prob_failure": 0.1, "impact_mean": 20.0},
            "B->C": {"prob_failure": 0.0, "impact_mean": 0.0},
        },
        "nodes": {}
    }

    graph = GraphAssembler.assemble(indexer, node_ids, fragility_map, reliability_report=report)

    # Imprimir resultados para verificación
    if not graph.edges:
        print("Graph has no edges")
        return

    for e in graph.edges:
        print(f"{e.edge_id} {e.w_survival} {e.w_expected_cost}")

if __name__ == "__main__":
    main()


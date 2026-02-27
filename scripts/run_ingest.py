import json
from src.bloque1.network import NetworkIndexer, Ingestor
from src.bloque1.topology import TopologyBuilder

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

indexer = NetworkIndexer()
ing = Ingestor(indexer)

nodes = load_json('examples/sample_nodes.json')
arcs = load_json('examples/sample_arcs.json')

s, f, _ = ing.load_nodes(nodes)
print("Nodes loaded:", s, "failed:", f)

s2, f2, _ = ing.load_arcs(arcs)
print("Arcs loaded:", s2, "failed:", f2)

report = ing.get_validation_report()
print("Validation report:", report)
print("Indexer counts:", indexer.node_count, indexer.arc_count)

tb = TopologyBuilder(indexer)
tb.build_topology()
package = tb.export_matrices(sparse=False)
print("Matrices exportadas:", {k: getattr(v, "shape", None) for k, v in package.items() if k in {"A", "C", "T", "K", "D"}})

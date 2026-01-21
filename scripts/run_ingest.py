import json
from src.bloque1.network import NetworkIndexer, Ingestor

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

indexer = NetworkIndexer()
ing = Ingestor(indexer)

nodes = load_json('examples/sample_nodes.json')
arcs = load_json('examples/sample_arcs.json')

s, f = ing.load_nodes(nodes)
print("Nodes loaded:", s, "failed:", f)

s2, f2 = ing.load_arcs(arcs)
print("Arcs loaded:", s2, "failed:", f2)

report = ing.get_validation_report()
print("Validation report:", report)
print("Indexer counts:", indexer.node_count, indexer.arc_count)

import numpy as np
from schema import Node, Edge, Graph, OptimizerConfig
from engines import DijkstraEngine

# 1. Crear nodos
nodes = [Node("A"), Node("B"), Node("C")]

# 2. Crear aristas
edges = [
    Edge(edge_id="e1", source="A", target="B", cost=5.0, distance=1.0, mode="truck"),
    Edge(edge_id="e2", source="B", target="C", cost=3.0, distance=1.0, mode="truck"),
    Edge(edge_id="e3", source="A", target="C", cost=10.0, distance=2.0, mode="truck"),
]

# 3. Crear indexer
edge_indexer = {edge.edge_id: i for i, edge in enumerate(edges)}

# 4. Crear grafo
graph = Graph(nodes=nodes, edges=edges, edge_indexer=edge_indexer)

# 5. Crear phi_vector (riesgo)
phi_vector = np.array([0.1, 0.2, 0.05])

# 6. Configuración del optimizador
config = OptimizerConfig(source_node_id="A", target_node_id="C", kappa=1.0)

# 7. Crear engine y resolver
engine = DijkstraEngine()
solution = engine.solve(graph, phi_vector, config)

# 8. Revisar resultados
print("Path:", solution.path)
print("Edges:", solution.edges)
print("Total cost:", solution.total_cost)
print("Optimized cost:", solution.optimized_cost)
print("Total risk:", solution.total_risk)

# 9. Comprobaciones automáticas (asserts)
assert solution.path == ["A", "B", "C"], "Path incorrecto"
assert solution.edges == ["e1", "e2"], "Edges incorrectos"
assert abs(solution.total_cost - 8.0) < 1e-6, "Total cost incorrecto"

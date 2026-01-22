# tests/test_topology.py
from src.bloque1.topology import GeometryEngine, TopologyBuilder

def test_haversine_zero():
    assert GeometryEngine.haversine(0, 0, 0, 0) == 0.0

def test_build_and_matrix(simple_indexer_fixture):
    idx = simple_indexer_fixture
    tb = TopologyBuilder(idx)
    tb.build_topology()
    mat, order = tb.get_adjacency_matrix(weighted=False)
    assert mat.shape[0] == len(order) == idx.node_count
    # NODE_0001 tiene 2 salidas
    i = order.index("NODE_0001")
    assert mat[i].sum() == 2

def test_factory_connectivity(simple_indexer_fixture):
    idx = simple_indexer_fixture
    tb = TopologyBuilder(idx)
    tb.build_topology()
    counts = tb.get_factory_connectivity()
    assert counts.get("NODE_0001") == 2

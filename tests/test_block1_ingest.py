from src.bloque1.network import NetworkIndexer, Ingestor

VALID_NODE = {
    "id": "NODE_0100",
    "lat": -34.5,
    "lon": -58.4,
    "supply": 0,
    "priority": 1,
    "metadata": {"source": "t", "version": "1.0", "timestamp": "2026-01-21T18:00:00Z"}
}

INVALID_NODE_COORD = {"id":"NODE_101","lat":-190,"lon":0,"metadata":{"source":"t","version":"1.0","timestamp":"2026-01-21T18:00:00Z"}}
VALID_NODE_2 = {"id":"NODE_200","lat":-34.6,"lon":-58.5,"metadata":{"source":"t","version":"1.0","timestamp":"2026-01-21T18:00:00Z"}}
ARC_MISSING_NODES = {"id":"ARC_100","origin":"NODE_X","destination":"NODE_Y","cost_profile":{"cost_type":"flat","params":{"variable_coef":1.0}}}

def test_load_node_valid():
    idx = NetworkIndexer()
    ing = Ingestor(idx)
    assert ing.load_node(VALID_NODE) is True
    report = ing.get_validation_report()
    assert report["node_count"] == 1
    assert report["error_count"] == 0

def test_load_node_invalid_coordinate():
    idx = NetworkIndexer()
    ing = Ingestor(idx)
    assert ing.load_node(INVALID_NODE_COORD) is False
    report = ing.get_validation_report()
    assert report["error_count"] >= 1
    assert idx.node_count == 0

def test_load_arc_missing_nodes():
    idx = NetworkIndexer()
    ing = Ingestor(idx)
    assert ing.load_arc(ARC_MISSING_NODES) is False
    report = ing.get_validation_report()
    assert report["error_count"] >= 1
    assert idx.arc_count == 0

def test_register_node_versioning_behavior():
    idx = NetworkIndexer()
    ing = Ingestor(idx)
    n1 = VALID_NODE.copy()
    n2 = VALID_NODE.copy()
    n2["metadata"] = {"source":"t","version":"1.0","timestamp":"2026-01-21T18:00:00Z"}
    assert ing.load_node(n1) is True
    assert ing.load_node(n2) is True
    assert idx.node_count == 1


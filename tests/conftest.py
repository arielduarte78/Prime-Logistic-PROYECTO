import pytest
from src.bloque1.network import NetworkIndexer
from src.bloque1.models import NodeRecord, ArcRecord

@pytest.fixture
def simple_indexer_fixture():
    idx = NetworkIndexer()
    # Crear 3 nodos: F1 (supply>0), N2, N3
    n1 = NodeRecord.from_dict({
        "id": "NODE_0001", "lat": -34.65, "lon": -58.45, "supply": 10,
        "priority": 1, "metadata": {"source": "test", "version": "1.0", "timestamp": "2026-01-21T18:00:00Z"}
    })
    n2 = NodeRecord.from_dict({
        "id": "NODE_0002", "lat": -34.66, "lon": -58.46, "supply": 0,
        "priority": 1, "metadata": {"source": "test", "version": "1.0", "timestamp": "2026-01-21T18:00:00Z"}
    })
    n3 = NodeRecord.from_dict({
        "id": "NODE_0003", "lat": -34.67, "lon": -58.47, "supply": 0,
        "priority": 1, "metadata": {"source": "test", "version": "1.0", "timestamp": "2026-01-21T18:00:00Z"}
    })
    idx.register_node(n1)
    idx.register_node(n2)
    idx.register_node(n3)

    # Arcos: F1 -> N2, F1 -> N3
    a1 = ArcRecord.from_dict({
        "id": "ARC_0001", "origin": "NODE_0001", "destination": "NODE_0002",
        "cost_profile": {"cost_type": "flat", "params": {"variable_coef": 1.0}},
        "speed_profile": {"default": 60},
        "metadata": {"source": "test", "version": "1.0", "timestamp": "2026-01-21T18:00:00Z"}
    })
    a2 = ArcRecord.from_dict({
        "id": "ARC_0002", "origin": "NODE_0001", "destination": "NODE_0003",
        "cost_profile": {"cost_type": "flat", "params": {"variable_coef": 1.0}},
        "speed_profile": {"default": 60},
        "metadata": {"source": "test", "version": "1.0", "timestamp": "2026-01-21T18:00:00Z"}
    })
    idx.register_arc(a1)
    idx.register_arc(a2)

    return idx

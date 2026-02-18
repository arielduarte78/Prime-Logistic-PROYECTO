# tests/test_prime_logistics_integration.py
import pytest
import networkx as nx
from src.bloque1.config import H3RouterConfig
from src.bloque1.h3_router import RouteEndpoint
from src.bloque1.cache_manager import SafeCacheManager
from src.bloque1.smart_ingestor import SmartLazyIngestor

@pytest.fixture
def config():
    # Config mínima para pruebas
    return H3RouterConfig(
        resolution=8,
        buffer_rings=1,
        local_rings=1,
        max_cells=200
    )

@pytest.fixture
def cache(tmp_path):
    # Cache temporal para no ensuciar data real
    return SafeCacheManager(cache_dir=tmp_path / "osm_cache")

def test_end_to_end_ingestion(config, cache):
    ingestor = SmartLazyIngestor(config, cache)

    # Endpoints de prueba (coordenadas reales de Buenos Aires)
    origin = RouteEndpoint(name="Plaza_Mayo", lat=-34.6083, lon=-58.3712)
    dest = RouteEndpoint(name="Obelisco", lat=-34.6037, lon=-58.3816)

    graph = ingestor.get_or_build_graph(origin, dest, mode="car")

    # Validaciones básicas
    assert isinstance(graph, nx.MultiDiGraph)
    assert graph.number_of_nodes() > 0
    assert graph.number_of_edges() > 0

    # Verificar que se guardó en caché y se puede recuperar
    cached = cache.load_graph(
        origin=origin.name,
        dest=dest.name,
        zoom=config.resolution,
        profile=config.buffer_rings,
        mode="car"
    )
    assert cached is not None
    assert isinstance(cached, nx.MultiDiGraph)

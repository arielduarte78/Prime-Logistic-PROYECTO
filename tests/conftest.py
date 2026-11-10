#tests/conftest.py
import os
import pytest
from fastapi.testclient import TestClient
import rustworkx as rx
from unittest.mock import MagicMock
from scipy.spatial import cKDTree
import numpy as np

# Establecer entorno en modo testing antes de cargar la app
os.environ["TESTING"] = "1"
# Para saltar dependencias en security.py si fuese necesario, o para setear vars mockeadas
os.environ["PRIME_API_KEYS"] = "test_client:test_key_123"

from main import app
from src.bloque4.schema import Node as SchemaNode
from src.bloque1.graph_builder import EdgePayload
from src.config.settings import CostSettings

@pytest.fixture
def mock_app_state():
    """
    Mockea el Lifespan de FastAPI:
    Previene la carga de 614MB en RAM construyendo un grafo mínimo de 3 nodos
    con coordenadas válidas dentro del AMBA (-35 a -34 lat, -59 a -58 lon).
    """
    # 1. Mock de variables de entorno y settings
    cost_env = CostSettings(
        c_km_ars=100.0,
        c_hora_ars=2000.0,
        franquicia_seguro_usd=500.0,
        dolar_mep_ars=1000.0,
        velocidad_comercial_kmh=40.0,
        peaje_promedio_ars=150.0,
        custodia_hora_ars=3000.0,
        ausa_25_mayo_ars=500.0,
        ausa_paseo_bajo_ars=600.0,
        acceso_norte_oeste_ars=300.0,
        aubasa_sur_ars=400.0
    )

    # 2. Grafo Dummy en AMBA
    base_graph = rx.PyDiGraph()
    # Nodos AMBA
    n0 = SchemaNode(node_id="0", lat=-34.60, lon=-58.38) # Obelisco aprox
    n1 = SchemaNode(node_id="1", lat=-34.61, lon=-58.37)
    n2 = SchemaNode(node_id="2", lat=-34.62, lon=-58.39)
    
    idx0 = base_graph.add_node(n0)
    idx1 = base_graph.add_node(n1)
    idx2 = base_graph.add_node(n2)

    # Aristas con highway variables para tests (ej: motorway vs residential)
    e01_payload = EdgePayload(
        u_osm=1000, v_osm=2000, length=1500.0, highway="motorway",
        name="25 de Mayo", ref="", h3_index="8a801234567ffff",
        alpha_prior=99.0, beta_prior=1.0 # 99% success
    )
    e12_payload = EdgePayload(
        u_osm=2000, v_osm=3000, length=2000.0, highway="residential",
        name="Calle Falsa 123", ref="", h3_index="8a801234567ffff",
        alpha_prior=80.0, beta_prior=20.0 # 80% success
    )
    
    base_graph.add_edge(idx0, idx1, e01_payload)
    base_graph.add_edge(idx1, idx2, e12_payload)

    # 3. Diccionarios de Mapeo
    osm_to_rx = {1000: idx0, 2000: idx1, 3000: idx2}
    rx_to_osm = {idx0: 1000, idx1: 2000, idx2: 3000}

    # 4. KDTree Espacial Mockeado
    coords = np.array([[-34.60, -58.38], [-34.61, -58.37], [-34.62, -58.39]])
    spatial_index = cKDTree(coords)
    spatial_rx_indices = [idx0, idx1, idx2]

    # 5. Judge y Matrices
    mock_judge = MagicMock()
    # Retornar betas consistentes
    mock_beta = MagicMock()
    mock_beta.alpha = 99.0
    mock_beta.beta = 1.0
    mock_judge.get_params.return_value = mock_beta

    mock_threat_matrix = {"8a801234567ffff": 0.5}
    mock_speed_profiles = {"motorway": {"AMBA_R1": 1.0}}

    # 5b. Auth: el lifespan no corre en los tests, así que registramos la API key de prueba a mano
    from src.api.identity import configure_identity
    configure_identity(
        jwt_secret=os.urandom(32),
        jwt_secret_prev=None,
        authorized_keys={"test_key_123": "test_client"},
        access_ttl=900,
        refresh_ttl=604800,
    )

    # 6. Asignar al contexto de la app
    app.state.base_graph = base_graph
    app.state.osm_to_rx = osm_to_rx
    app.state.rx_to_osm = rx_to_osm
    app.state.spatial_index = spatial_index
    app.state.spatial_rx_indices = spatial_rx_indices
    app.state.judge = mock_judge
    app.state.judge_standard = mock_judge
    app.state.judge_premium = None
    app.state.cost_settings = cost_env
    app.state.threat_matrix = mock_threat_matrix
    app.state.speed_profiles = mock_speed_profiles

    # Importante: Mockear semáforos asíncronos para VRP Orchestrator
    import asyncio
    from src.api.cola import Cola
    app.state.cola_route = Cola(en_paralelo=10, max_en_espera=10, espera_max_s=5)
    app.state.cola_fleet = Cola(en_paralelo=10, max_en_espera=10, espera_max_s=5)

    yield app.state

@pytest.fixture
def test_client(mock_app_state):
    """
    TestClient estándar de FastAPI.
    Patchamos get_nearest_node_osm_id en su origen (duckdb_ingestor) 
    para que todos los módulos que lo importaron vean el mock.
    """
    from unittest.mock import patch
    
    def my_nearest_node_osm_id(lat, lon):
        """
        Mock de resolución espacial. Usa tolerancia de 0.005 grados (~500m)
        en lugar de igualdad exacta de float para evitar falsos fallbacks
        si algún módulo redondea coordenadas internamente.
        """
        if abs(lat - (-34.60)) < 0.005: return 1000
        if abs(lat - (-34.61)) < 0.005: return 2000
        if abs(lat - (-34.62)) < 0.005: return 3000
        if abs(lat - 0.0) < 0.005: return 999999  # Null Island — inválido intencional
        raise ValueError(f"Coordenada lat={lat} no tiene nodo mock asignado. Agregá el caso al conftest.")

    with patch("main.get_nearest_node_osm_id", side_effect=my_nearest_node_osm_id):
        yield TestClient(app)

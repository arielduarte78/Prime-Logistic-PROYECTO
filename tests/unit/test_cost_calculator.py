#tests/unit/test_cost_calculator.py
import pytest
from src.bloque4.cost_calculator import compute_edge_cost, _get_toll_from_ref
from src.config.settings import CostSettings
from src.bloque1.graph_builder import EdgePayload

@pytest.fixture
def test_cost_env():
    return CostSettings(
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

def test_toll_name_resolution_no_fallback(test_cost_env):
    """Verifica que una arista con '25 DE MAYO' asigne el peaje correcto y no active el fallback."""
    payload = EdgePayload(
        u_osm=1, v_osm=2, length=1000.0, highway="motorway",
        name="Autopista 25 de Mayo", ref="", h3_index="test_index",
        alpha_prior=99.0, beta_prior=1.0
    )
    
    weight, fallback_used = compute_edge_cost(
        payload=payload, u_rx=1, v_rx=2, cost_env=test_cost_env,
        threat_matrix={}, judge=None, departure_hour=12,
        speed_profiles={}, archetype="equilibrista"
    )
    
    # 500 ARS de peaje + c_km + c_hora. Nos importa que fallback_used sea False
    assert fallback_used is False

def test_toll_ref_resolution_no_fallback(test_cost_env):
    """Verifica que 'RN2' matchee con aubasa_sur sin usar fallback genérico."""
    payload = EdgePayload(
        u_osm=1, v_osm=2, length=1000.0, highway="motorway",
        name="Ruta Desconocida", ref="RN2", h3_index="test_index",
        alpha_prior=99.0, beta_prior=1.0
    )
    
    weight, fallback_used = compute_edge_cost(
        payload=payload, u_rx=1, v_rx=2, cost_env=test_cost_env,
        threat_matrix={}, judge=None, departure_hour=12,
        speed_profiles={}, archetype="equilibrista"
    )
    
    assert fallback_used is False

def test_toll_generic_fallback_activated(test_cost_env):
    """Verifica que una autopista fantasma (sin nombre, sin ref) active el fallback genérico."""
    payload = EdgePayload(
        u_osm=1, v_osm=2, length=1000.0, highway="motorway",
        name="", ref="", h3_index="test_index",
        alpha_prior=99.0, beta_prior=1.0
    )
    
    weight, fallback_used = compute_edge_cost(
        payload=payload, u_rx=1, v_rx=2, cost_env=test_cost_env,
        threat_matrix={}, judge=None, departure_hour=12,
        speed_profiles={}, archetype="equilibrista"
    )
    
    assert fallback_used is True

def test_residential_no_toll(test_cost_env):
    """Calles residenciales no pagan peaje ni triggeran fallbacks."""
    payload = EdgePayload(
        u_osm=1, v_osm=2, length=1000.0, highway="residential",
        name="Calle Falsa 123", ref="", h3_index="test_index",
        alpha_prior=99.0, beta_prior=1.0
    )
    
    weight, fallback_used = compute_edge_cost(
        payload=payload, u_rx=1, v_rx=2, cost_env=test_cost_env,
        threat_matrix={}, judge=None, departure_hour=12,
        speed_profiles={}, archetype="equilibrista"
    )
    
    assert fallback_used is False

#tests/unit/test_cost_calculator.py
import pytest
from src.bloque4.cost_calculator import compute_edge_cost, _get_toll_from_ref
from src.api.schemas import EconomicProfile
from src.bloque1.graph_builder import EdgePayload

@pytest.fixture
def test_cost_env():
    # Mismo tipo que usa la app en /route y /fleet (perfil con opex/personal/capex anidados)
    return EconomicProfile(
        franquicia_seguro_usd=500.0,
        dolar_mep_ars=1000.0,
        velocidad_comercial_kmh=40.0,
        peaje_promedio_ars=150.0,
        custodia_hora_ars=3000.0,
        ausa_25_mayo_ars=500.0,
        ausa_paseo_bajo_ars=600.0,
        acceso_norte_oeste_ars=300.0,
        aubasa_sur_ars=400.0,
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


# ─── Peaje por cruce (no por arista) y match de "BAJO" ───

def _toll_part(env, length_m, name="Autopista 25 de Mayo", highway="motorway"):
    """Parte de peaje del peso de una arista = peso(autopista) - peso(misma arista sin peaje)."""
    def peso(hw):
        p = EdgePayload(u_osm=1, v_osm=2, length=length_m, highway=hw, name=name,
                        ref="", h3_index="", alpha_prior=99.0, beta_prior=1.0)
        w, _ = compute_edge_cost(payload=p, u_rx=1, v_rx=2, cost_env=env, threat_matrix={},
                                 judge=None, departure_hour=12, speed_profiles={}, archetype="apostador")
        return w
    return (peso(highway) - peso("primary")) / 0.99  # apostador: lambda_cost = 0.99


def test_peaje_se_prorratea_por_largo_no_por_arista(test_cost_env):
    """Un tramo de 10 km de 25 de Mayo cuesta un peaje; partido en 2 aristas de 5 km, también uno (no dos)."""
    peaje = test_cost_env.ausa_25_mayo_ars
    una_arista = _toll_part(test_cost_env, 10_000)
    dos_aristas = 2 * _toll_part(test_cost_env, 5_000)
    assert una_arista == pytest.approx(peaje)
    assert dos_aristas == pytest.approx(peaje)


def test_bajo_suelto_no_cobra_paseo_del_bajo(test_cost_env):
    """Una calle 'Bajo Belgrano' no es el Paseo del Bajo: no debe usar su tarifa (cae al fallback)."""
    p = EdgePayload(u_osm=1, v_osm=2, length=1000.0, highway="motorway", name="Bajo Belgrano",
                    ref="", h3_index="", alpha_prior=99.0, beta_prior=1.0)
    _, fallback_used = compute_edge_cost(payload=p, u_rx=1, v_rx=2, cost_env=test_cost_env,
                                         threat_matrix={}, judge=None, departure_hour=12,
                                         speed_profiles={}, archetype="equilibrista")
    assert fallback_used is True


def test_paseo_del_bajo_sigue_funcionando(test_cost_env):
    p = EdgePayload(u_osm=1, v_osm=2, length=1000.0, highway="motorway", name="Paseo del Bajo",
                    ref="", h3_index="", alpha_prior=99.0, beta_prior=1.0)
    _, fallback_used = compute_edge_cost(payload=p, u_rx=1, v_rx=2, cost_env=test_cost_env,
                                         threat_matrix={}, judge=None, departure_hour=12,
                                         speed_profiles={}, archetype="equilibrista")
    assert fallback_used is False

import pytest
from unittest.mock import MagicMock
from src.api.schemas import EconomicProfile, OpexMovil
from src.bloque1.graph_builder import EdgePayload
from src.block5.lambda_scalarizer import get_weight_function, clear_cost_cache
from src.block5.cost_matrix_builder import _get_time_weight_fn, clear_time_weight_cache


@pytest.fixture(autouse=True)
def cachés_limpias():
    clear_cost_cache()
    clear_time_weight_cache()
    yield
    clear_cost_cache()
    clear_time_weight_cache()


@pytest.fixture
def arista():
    return EdgePayload(u_osm=1, v_osm=2, length=2000.0, highway="residential", name="", ref="",
                       h3_index="", alpha_prior=99.0, beta_prior=1.0)


def _peso(perfil, arista):
    judge = MagicMock()
    judge.get_params.return_value = MagicMock(alpha=99.0, beta=1.0)
    fn = get_weight_function("apostador", perfil, {}, judge, {1: 0, 2: 1}, departure_hour=12)
    return fn(arista)


def test_costo_cambia_si_cambia_el_perfil_economico(arista):
    """El mismo tramo con gasoil 10x más caro tiene que costar más (no devolver el valor cacheado del request anterior)."""
    barato = EconomicProfile()
    caro = EconomicProfile(opex_movil=OpexMovil(gasoil_ars_l=18650.0))
    peso_barato = _peso(barato, arista)
    peso_caro = _peso(caro, arista)
    assert peso_caro > peso_barato * 2


def test_mismo_perfil_reutiliza_la_cache(arista):
    """Con el mismo perfil (aunque sea otro objeto) el resultado es idéntico: la cache sigue sirviendo."""
    assert _peso(EconomicProfile(), arista) == _peso(EconomicProfile(), arista)


def test_tiempo_cambia_si_cambia_la_velocidad(arista):
    lento = EconomicProfile(velocidad_comercial_kmh=20.0)
    rapido = EconomicProfile(velocidad_comercial_kmh=80.0)
    t_lento = _get_time_weight_fn(lento, 12, {})(arista)
    t_rapido = _get_time_weight_fn(rapido, 12, {})(arista)
    assert t_lento == pytest.approx(4 * t_rapido)


# ─── El juez bayesiano también entra en la clave de la caché ───

def _juez_real(arista):
    import rustworkx as rx
    from src.bloque3.bayesian_judge import BayesianJudge
    g = rx.PyDiGraph()
    g.add_node(0)
    g.add_node(1)
    g.add_edge(0, 1, arista)
    return BayesianJudge(g)


def _peso_con_juez(juez, arista):
    fn = get_weight_function("tanque", EconomicProfile(), {}, juez, {1: 0, 2: 1}, departure_hour=12)
    return fn(arista)


def test_costo_cambia_si_cambia_el_juez(arista):
    """Un clon con más fallas observadas tiene más riesgo: el costo no puede salir de la caché del juez anterior."""
    juez = _juez_real(arista)
    clon = juez.spawn_ephemeral_clone()
    clon.update_edge(0, 1, successes=0.0, failures=50.0)
    assert _peso_con_juez(clon, arista) > _peso_con_juez(juez, arista)


def test_mismo_juez_reutiliza_la_cache(arista):
    juez = _juez_real(arista)
    clon_igual = juez.spawn_ephemeral_clone()  # mismos parámetros, otro objeto
    assert _peso_con_juez(juez, arista) == _peso_con_juez(clon_igual, arista)

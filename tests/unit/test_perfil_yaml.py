import pytest
import yaml
from src.api.schemas import EconomicProfile
from src.config import settings


@pytest.fixture
def yaml_real():
    with open(settings.CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_sin_perfil_del_cliente_se_usa_el_yaml(yaml_real):
    p = settings.resolve_profile(None)
    assert p.velocidad_comercial_kmh == yaml_real["costos"]["velocidad_comercial_kmh"]
    assert p.franquicia_seguro_usd == yaml_real["costos"]["franquicia_seguro_usd"]
    assert p.dolar_mep_ars == yaml_real["costos"]["dolar_mep_ars"]
    assert p.peaje_promedio_ars == yaml_real["peajes"]["promedio_ars"]
    assert p.ausa_25_mayo_ars == yaml_real["peajes"]["ausa_25_mayo_ars"]
    assert p.custodia_hora_ars == yaml_real["custodia"]["tarifa_hora_ars"]
    assert p.opex_movil.gasoil_ars_l == yaml_real["opex_movil"]["gasoil_ars_l"]
    assert p.personal.jornada_mensual_hs == yaml_real["personal"]["jornada_mensual_hs"]
    assert p.capex.vida_util_meses == yaml_real["capex"]["vida_util_meses"]


def test_el_cliente_pisa_solo_lo_que_manda(yaml_real):
    """Lo que el cliente manda gana; lo que no manda sale del YAML (no de los defaults de schemas.py)."""
    cliente = EconomicProfile(dolar_mep_ars=2000.0, opex_movil={"gasoil_ars_l": 3000.0})
    p = settings.resolve_profile(cliente)
    assert p.dolar_mep_ars == 2000.0
    assert p.opex_movil.gasoil_ars_l == 3000.0
    assert p.opex_movil.consumo_l_km == yaml_real["opex_movil"]["consumo_l_km"]  # no lo mandó
    assert p.velocidad_comercial_kmh == yaml_real["costos"]["velocidad_comercial_kmh"]  # no lo mandó


def test_cambiar_el_yaml_cambia_el_perfil(monkeypatch, yaml_real):
    cambiado = {**yaml_real, "costos": {**yaml_real["costos"], "velocidad_comercial_kmh": 33.0}}
    monkeypatch.setattr(settings, "_cargar_yaml", lambda: cambiado)
    assert settings.resolve_profile(None).velocidad_comercial_kmh == 33.0


def test_health_lee_el_yaml(test_client, monkeypatch, yaml_real):
    r = test_client.get("/health").json()
    perfil = settings.resolve_profile(None)
    assert r["ckm_ars"] == pytest.approx(settings.costo_por_km(perfil), abs=0.01)
    assert r["ch_ars"] == pytest.approx(settings.costo_por_hora(perfil), abs=0.01)
    # si cambia el YAML, /health cambia (no está hardcodeado)
    cambiado = {**yaml_real, "opex_movil": {**yaml_real["opex_movil"], "gasoil_ars_l": 3730.0}}
    monkeypatch.setattr(settings, "_cargar_yaml", lambda: cambiado)
    r2 = test_client.get("/health").json()
    assert r2["ckm_ars"] > r["ckm_ars"] * 1.5

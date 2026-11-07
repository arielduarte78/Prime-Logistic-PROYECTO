#src/config/settings.py
import copy
import functools
import yaml
from typing import Optional
from pathlib import Path
from dataclasses import dataclass

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "cost_params.yaml"

@dataclass
class CostSettings:
    c_km_ars: float
    c_hora_ars: float
    franquicia_seguro_usd: float
    dolar_mep_ars: float
    velocidad_comercial_kmh: float
    peaje_promedio_ars: float
    custodia_hora_ars: float

    ausa_25_mayo_ars: float 
    ausa_paseo_bajo_ars: float 
    acceso_norte_oeste_ars: float 
    aubasa_sur_ars: float

    @property
    def franquicia_ars(self) -> float:
        return self.franquicia_seguro_usd * self.dolar_mep_ars

    @property
    def c_minuto_ars(self) -> float:
        return self.c_hora_ars / 60.0

def load_cost_settings() -> CostSettings:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Configuración no encontrada: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return CostSettings(
        c_km_ars=float(data["costos"]["c_km_ars"]),
        c_hora_ars=float(data["costos"]["c_hora_ars"]),
        franquicia_seguro_usd=float(data["costos"]["franquicia_seguro_usd"]),
        dolar_mep_ars=float(data["costos"]["dolar_mep_ars"]),
        velocidad_comercial_kmh=float(data["costos"]["velocidad_comercial_kmh"]),
        peaje_promedio_ars=float(data["peajes"]["promedio_ars"]),
        custodia_hora_ars=float(data["custodia"]["tarifa_hora_ars"]),
        ausa_25_mayo_ars=float(data["peajes"]["ausa_25_mayo_ars"]),
        ausa_paseo_bajo_ars=float(data["peajes"]["ausa_paseo_bajo_ars"]),
        acceso_norte_oeste_ars=float(data["peajes"]["acceso_norte_oeste_ars"]),
        aubasa_sur_ars=float(data["peajes"]["aubasa_sur_ars"])
    )



# ─── Perfil económico: cost_params.yaml es la única fuente de valores por defecto ───

@functools.lru_cache(maxsize=1)
def _cargar_yaml() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _perfil_desde_yaml() -> dict:
    """Arma el perfil económico (con la forma de EconomicProfile) a partir del YAML."""
    y = copy.deepcopy(_cargar_yaml())
    return {
        "opex_movil": y["opex_movil"],
        "personal": y["personal"],
        "capex": y["capex"],
        "dolar_mep_ars": y["costos"]["dolar_mep_ars"],
        "velocidad_comercial_kmh": y["costos"]["velocidad_comercial_kmh"],
        "franquicia_seguro_usd": y["costos"]["franquicia_seguro_usd"],
        "peaje_promedio_ars": y["peajes"]["promedio_ars"],
        "custodia_hora_ars": y["custodia"]["tarifa_hora_ars"],
        "ausa_25_mayo_ars": y["peajes"]["ausa_25_mayo_ars"],
        "ausa_paseo_bajo_ars": y["peajes"]["ausa_paseo_bajo_ars"],
        "acceso_norte_oeste_ars": y["peajes"]["acceso_norte_oeste_ars"],
        "aubasa_sur_ars": y["peajes"]["aubasa_sur_ars"],
    }


def _mezclar(base: dict, cambios: dict) -> None:
    for clave, valor in cambios.items():
        if isinstance(valor, dict) and isinstance(base.get(clave), dict):
            _mezclar(base[clave], valor)
        else:
            base[clave] = valor


def resolve_profile(cliente: Optional["EconomicProfile"] = None) -> "EconomicProfile":  # noqa: F821
    """
    Perfil que usan /route y /fleet: valores del YAML, pisados SOLO por los campos
    que el cliente mandó explícitamente (los que no mandó no toman el default de schemas.py).
    """
    from src.api.schemas import EconomicProfile
    datos = _perfil_desde_yaml()
    if cliente is not None:
        _mezclar(datos, cliente.model_dump(exclude_unset=True))
    return EconomicProfile.model_validate(datos)


def costo_por_km(perfil) -> float:
    """CKM = gasoil * consumo + neumáticos + mantenimiento  (ARS por km)."""
    o = perfil.opex_movil
    return o.gasoil_ars_l * o.consumo_l_km + o.neumaticos_km_ars + o.mantenimiento_km_ars


def costo_por_hora(perfil) -> float:
    """CH = (costo laboral + costo estructural) / horas del mes  (ARS por hora)."""
    p, c = perfil.personal, perfil.capex
    laboral = (p.sueldo_basico_ars * p.cargas_sociales_factor + p.bono_mensual_ars
               + p.viatico_dia_ars * 22 + p.provision_sac_vacaciones_ars)
    amortizacion = c.valor_unidad_ars * (1 - c.valor_recupero_pct) / c.vida_util_meses
    estructural = amortizacion + c.seguros_patentes_mes_ars + c.telemetria_mes_ars
    return (laboral + estructural) / p.jornada_mensual_hs

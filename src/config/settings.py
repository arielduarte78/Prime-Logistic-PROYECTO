#src/config/settings.py
import yaml
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

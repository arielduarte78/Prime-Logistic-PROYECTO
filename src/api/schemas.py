#src/api/schemas.py
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any

class OpexMovil(BaseModel):
    gasoil_ars_l: float = 1865.0
    consumo_l_km: float = 0.33
    neumaticos_km_ars: float = 57.0
    mantenimiento_km_ars: float = 135.4

class PersonalProfile(BaseModel):
    sueldo_basico_ars: float = 1007060.0
    cargas_sociales_factor: float = 1.45
    bono_mensual_ars: float = 210000.0
    viatico_dia_ars: float = 15671.16
    jornada_mensual_hs: float = 176.0
    provision_sac_vacaciones_ars: float = 121686.0

class CapexProfile(BaseModel):
    valor_unidad_ars: float = 111800000.0
    vida_util_meses: float = 120.0
    valor_recupero_pct: float = 0.20
    seguros_patentes_mes_ars: float = 320000.0
    telemetria_mes_ars: float = 165000.0

class EconomicProfile(BaseModel):
    opex_movil: OpexMovil = Field(default_factory=OpexMovil)
    personal: PersonalProfile = Field(default_factory=PersonalProfile)
    capex: CapexProfile = Field(default_factory=CapexProfile)
    
    # Legacy / Aux fields (Defaults seguros para evitar crashes en sumas)
    dolar_mep_ars: float = 1415.52
    velocidad_comercial_kmh: float = 40.0
    peaje_promedio_ars: float = 1200.0
    custodia_hora_ars: float = 0.0
    ausa_25_mayo_ars: float = 1200.0
    ausa_paseo_bajo_ars: float = 1200.0
    acceso_norte_oeste_ars: float = 1300.0
    aubasa_sur_ars: float = 900.0
    franquicia_seguro_usd: float = 1500.0

class VehicleInput(BaseModel):
    id: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$', max_length=50)
    origin_lat: float = Field(..., ge=-90.0, le=90.0)
    origin_lon: float = Field(..., ge=-180.0, le=180.0)
    capacity_tons: float = Field(..., ge=0.0, le=1000.0)
    max_shift_minutes: int = Field(default=480, ge=60, le=1440)
    departure_time: Optional[str] = None
    overtime_cost_hr: Optional[float] = None

class DestinationInput(BaseModel):
    id: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$', max_length=50)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    demand_tons: float = Field(..., ge=0.0, le=1000.0)
    tw_start_min: int = Field(default=0, ge=0, le=1440)
    tw_end_min: int = Field(default=1440, ge=0, le=1440)
    service_time_min: int = Field(default=0, ge=0, le=240)
    referencia: Optional[str] = None

    @model_validator(mode='after')
    def validate_time_window(self):
        if self.tw_end_min <= self.tw_start_min:
            raise ValueError("tw_end_min debe ser mayor que tw_start_min")
        return self

class StopSchedule(BaseModel):
    destination_id: str
    suggested_arrival_min: Optional[int] = None
    earliest_arrival_min: Optional[int] = None
    latest_arrival_min: Optional[int] = None
    suggested_arrival_hhmm: Optional[str] = None

class RouteRequest(BaseModel):
    vehicles: List[VehicleInput] = Field(..., min_length=1, max_length=10)
    destinations: List[DestinationInput] = Field(..., min_length=1, max_length=50)
    departure_time: Optional[str] = Field(None, max_length=30)
    stochastic_mode: bool = False
    economic_profile: Optional[EconomicProfile] = None

class CostBreakdown(BaseModel):
    distancia_km: float
    consumo_litros: float
    precio_gasoil_ars: float
    consumo_l_por_km: float
    costo_combustible_ars: float
    costo_neumaticos_ars: float
    costo_mantenimiento_ars: float
    ckm_total_ars: float

    duracion_horas: float
    costo_laboral_hora: float
    costo_amort_hora: float
    costo_seguros_hora: float
    costo_telemetria_hora: float
    ch_total_ars: float

    peajes_cruzados: List[Dict[str, Any]] = []
    costo_peajes_ars: float
    viatico_ars: float

    opex_distance_ars: float = 0.0
    opex_time_ars: float = 0.0
    capex_amortization_ars: float = 0.0
    fixed_costs_ars: float = 0.0
    custodia_ars: float = 0.0
    exposure_risk_ars: float = 0.0
    executive_variance_analysis: List[str] = []

    costo_total_ars: float
    costo_total_usd: float
    dolar_mep: float = 1415.52
    fuente_precios: str = "CFO-Grade / Mar 2026 Audit"

class ParetoResult(BaseModel):
    archetype: str
    w_survival: float
    w_expected_cost: float
    route_nodes: List[int]
    route_coordinates: List[List[float]] = []
    confidence: float
    cost_breakdown: Optional[CostBreakdown] = None

class RouteResponse(BaseModel):
    processing_time_ms: float
    total_edges: int
    toll_fallback_edges: int = 0
    pareto_solutions: List[ParetoResult]

class FleetRequest(BaseModel):
    vehicles: List[VehicleInput] = Field(..., min_length=1, max_length=20)
    destinations: List[DestinationInput] = Field(..., min_length=1, max_length=100)
    allowed_archetypes: List[str] = Field(default=["equilibrista"], max_length=4)
    time_limit_seconds: int = Field(default=10, ge=1, le=60)
    departure_time: Optional[str] = Field(None, max_length=30)
    stochastic_mode: bool = False
    economic_profile: Optional[EconomicProfile] = None
    shift_start_minutes: int = Field(default=480, ge=0, le=1440)

class FleetResponse(BaseModel):
    subgraph_edges: int
    total_time_ms: float
    phase4_total_legs: int
    toll_fallback_edges: int = 0
    plans: Dict[str, Any]
    time_windows_enforced: bool = False
    shift_limit_enforced: bool = False

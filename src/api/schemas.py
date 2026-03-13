#src/api/schemas.py
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any

class EconomicProfile(BaseModel):
    c_km_ars: Optional[float] = None
    c_hora_ars: Optional[float] = None
    franquicia_seguro_usd: Optional[float] = None
    dolar_mep_ars: Optional[float] = None
    velocidad_comercial_kmh: Optional[float] = None
    peaje_promedio_ars: Optional[float] = None
    custodia_hora_ars: Optional[float] = None
    ausa_25_mayo_ars: Optional[float] = None
    ausa_paseo_bajo_ars: Optional[float] = None
    acceso_norte_oeste_ars: Optional[float] = None
    aubasa_sur_ars: Optional[float] = None

class VehicleInput(BaseModel):
    id: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$', max_length=50)
    origin_lat: float = Field(..., ge=-90.0, le=90.0)
    origin_lon: float = Field(..., ge=-180.0, le=180.0)
    capacity_tons: float = Field(..., ge=0.0, le=1000.0)
    max_shift_minutes: int = Field(default=480, ge=60, le=1440)

class DestinationInput(BaseModel):
    id: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$', max_length=50)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    demand_tons: float = Field(..., ge=0.0, le=1000.0)
    tw_start_min: int = Field(default=0, ge=0, le=1440)
    tw_end_min: int = Field(default=1440, ge=0, le=1440)
    service_time_min: int = Field(default=0, ge=0, le=240)

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
    # Componentes de CKM
    distancia_km: float
    consumo_litros: float
    precio_gasoil_ars: float = 1865.0     # Ponderado Puma+Axion Mar 2026
    consumo_l_por_km: float = 0.33        # Stop-and-go AMBA camión 15t
    costo_combustible_ars: float
    costo_neumaticos_ars: float
    costo_mantenimiento_ars: float
    ckm_total_ars: float = 807.85          # Costo por km total

    # Componentes de CH
    duracion_horas: float
    costo_laboral_hora: float = 12140.27  # CCT 40/89 Mar 2026
    costo_amort_hora: float = 4234.84     # CAPEX Atego 1721
    costo_seguros_hora: float = 1818.18   # SSN Ene 2026 + patentes
    costo_telemetria_hora: float = 937.50  # GPS+ADAS+vigilancia
    ch_total_ars: float = 19130.79         # Costo por hora total

    # Peajes dinámicos (TDVRP)
    peajes_cruzados: List[Dict[str, Any]] = []
    costo_peajes_ars: float
    viatico_ars: float = 15671.16

    # Totales
    costo_total_ars: float
    costo_total_usd: float
    dolar_mep: float = 1415.52             # MEP 13 Mar 2026
    fuente_precios: str = "FADEEAC/AUSA/CCT40-89 Mar 2026"

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


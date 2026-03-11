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

class ParetoResult(BaseModel):
    archetype: str
    w_survival: float
    w_expected_cost: float
    route_nodes: List[int]
    route_coordinates: List[List[float]] = []
    confidence: float

class RouteResponse(BaseModel):
    processing_time_ms: float
    total_edges: int
    pareto_solutions: List[ParetoResult]

class FleetRequest(BaseModel):
    vehicles: List[VehicleInput] = Field(..., min_length=1, max_length=20)
    destinations: List[DestinationInput] = Field(..., min_length=1, max_length=100)
    allowed_archetypes: List[str] = Field(default=["equilibrista"], max_length=4)
    time_limit_seconds: int = Field(default=10, ge=1, le=60)
    departure_time: Optional[str] = Field(None, max_length=30)
    stochastic_mode: bool = False
    economic_profile: Optional[EconomicProfile] = None

class FleetResponse(BaseModel):
    subgraph_edges: int
    total_time_ms: float
    phase4_total_legs: int
    plans: Dict[str, Any]
    time_windows_enforced: bool = False
    shift_limit_enforced: bool = False


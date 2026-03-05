#schemas.py
from pydantic import BaseModel
from typing import List, Optional

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
    id: str
    capacity_tons: float
    origin_lat: float
    origin_lon: float

class DestinationInput(BaseModel):
    id: str
    demand_tons: float
    lat: float
    lon: float

class RouteRequest(BaseModel):
    vehicles: List[VehicleInput]
    destinations: List[DestinationInput]
    risk_profile: str = "balanced"
    economic_profile: Optional[EconomicProfile] = None

class ParetoResult(BaseModel):
    archetype: str
    w_survival: float
    w_expected_cost: float
    route_nodes: List[int]
    confidence: float

class RouteResponse(BaseModel):
    processing_time_ms: float
    total_edges: int
    pareto_solutions: List[ParetoResult]

#schemas.py
from pydantic import BaseModel
from typing import List

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

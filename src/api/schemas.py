#src/api/schemas.py
"""
Contratos de datos del perímetro API — Prime Logistics Engine.

ISO 27001 Control A.14.2: Validación de Tipos Estricta.
Todos los modelos de ingreso HTTP operan en Pydantic strict mode.
Los campos financieros (ARS) utilizan restricciones de rango para
evitar inyección de valores físicamente imposibles o sabotaje de P&L.

CISO Directive: Los campos financieros mantienen float con rangos
explícitos (ge/le) para evitar redondeos silenciosos.  No se acepta
coerción de tipos (strict=True bloquea "3.5" → 3.5).
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any
import re

# ─────────────────────────────────────────────────────────
# PERFILES ECONÓMICOS (Ingreso — Strict + Rangos Físicos)
# ─────────────────────────────────────────────────────────

class OpexMovil(BaseModel):
    model_config = ConfigDict(strict=True)

    gasoil_ars_l: float = Field(default=1865.0, ge=100.0, le=50000.0,
        description="Precio gasoil ARS/litro. Rango realista mercado AR.")
    consumo_l_km: float = Field(default=0.33, ge=0.01, le=5.0,
        description="Consumo litros/km. Restricción física flota terrestre.")
    neumaticos_km_ars: float = Field(default=57.0, ge=0.0, le=5000.0)
    mantenimiento_km_ars: float = Field(default=135.4, ge=0.0, le=10000.0)

class PersonalProfile(BaseModel):
    model_config = ConfigDict(strict=True)

    sueldo_basico_ars: float = Field(default=1007060.0, ge=1.0, le=100000000.0,
        description="Sueldo básico mensual ARS. ge=1 previene salario cero.")
    cargas_sociales_factor: float = Field(default=1.45, ge=1.0, le=3.0,
        description="Multiplicador cargas sociales. Rango legal 1.0-3.0.")
    bono_mensual_ars: float = Field(default=210000.0, ge=0.0, le=50000000.0)
    viatico_dia_ars: float = Field(default=15671.16, ge=0.0, le=1000000.0)
    jornada_mensual_hs: float = Field(default=176.0, ge=1.0, le=744.0,
        description="Horas/mes. ge=1 previene división por cero en CH.")
    provision_sac_vacaciones_ars: float = Field(default=121686.0, ge=0.0, le=50000000.0)

class CapexProfile(BaseModel):
    model_config = ConfigDict(strict=True)

    valor_unidad_ars: float = Field(default=111800000.0, ge=1.0, le=10000000000.0)
    vida_util_meses: float = Field(default=120.0, ge=1.0, le=600.0,
        description="ge=1 previene división por cero en amortización.")
    valor_recupero_pct: float = Field(default=0.20, ge=0.0, le=1.0)
    seguros_patentes_mes_ars: float = Field(default=320000.0, ge=0.0, le=50000000.0)
    telemetria_mes_ars: float = Field(default=165000.0, ge=0.0, le=10000000.0)

class EconomicProfile(BaseModel):
    model_config = ConfigDict(strict=True)

    opex_movil: OpexMovil = Field(default_factory=OpexMovil)
    personal: PersonalProfile = Field(default_factory=PersonalProfile)
    capex: CapexProfile = Field(default_factory=CapexProfile)
    
    # Legacy / Aux fields con rangos de seguridad
    dolar_mep_ars: float = Field(default=1415.52, ge=100.0, le=100000.0,
        description="ge=100 previene división por cero/valor absurdo en conversión USD.")
    velocidad_comercial_kmh: float = Field(default=40.0, ge=5.0, le=120.0,
        description="Restricción física: camión entre 5 y 120 km/h.")
    peaje_promedio_ars: float = Field(default=1200.0, ge=0.0, le=100000.0)
    custodia_hora_ars: float = Field(default=0.0, ge=0.0, le=1000000.0)
    ausa_25_mayo_ars: float = Field(default=1200.0, ge=0.0, le=100000.0)
    ausa_paseo_bajo_ars: float = Field(default=1200.0, ge=0.0, le=100000.0)
    acceso_norte_oeste_ars: float = Field(default=1300.0, ge=0.0, le=100000.0)
    aubasa_sur_ars: float = Field(default=900.0, ge=0.0, le=100000.0)
    franquicia_seguro_usd: float = Field(default=1500.0, ge=0.0, le=100000.0)

    @model_validator(mode='after')
    def validate_physical_coherence(self):
        """
        Validación cross-field: previene inyección semántica que destruya
        la matriz de costos sin violar restricciones individuales.
        """
        if self.opex_movil.consumo_l_km <= 0:
            raise ValueError("consumo_l_km debe ser positivo (restricción física)")
        if self.personal.jornada_mensual_hs <= 0:
            raise ValueError("jornada_mensual_hs debe ser positiva (previene div/0 en CH)")
        if self.capex.vida_util_meses <= 0:
            raise ValueError("vida_util_meses debe ser positiva (previene div/0 en amortización)")
        if self.dolar_mep_ars <= 0:
            raise ValueError("dolar_mep_ars debe ser positivo (previene div/0 en conversión USD)")
        return self

# ─────────────────────────────────────────────────────────
# MODELOS DE VEHÍCULOS Y DESTINOS (Ingreso — Strict)
# ─────────────────────────────────────────────────────────

_DEPARTURE_TIME_REGEX = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')

class VehicleInput(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str = Field(..., pattern=r'^[a-zA-Z0-9_-]+$', max_length=50)
    origin_lat: float = Field(..., ge=-90.0, le=90.0)
    origin_lon: float = Field(..., ge=-180.0, le=180.0)
    capacity_tons: float = Field(..., ge=0.0, le=1000.0)
    max_shift_minutes: int = Field(default=480, ge=60, le=1440)
    departure_time: Optional[str] = Field(default=None, max_length=5)
    overtime_cost_hr: Optional[float] = Field(default=None, ge=0.0, le=10000000.0)

    @field_validator('departure_time')
    @classmethod
    def validate_departure_format(cls, v):
        """ISO 27001 A.14.2: Formato estricto HH:MM para prevenir inyección."""
        if v is not None and not _DEPARTURE_TIME_REGEX.match(v):
            raise ValueError(
                f"departure_time debe ser formato HH:MM (00:00-23:59), recibido: '{v}'"
            )
        return v

class DestinationInput(BaseModel):
    model_config = ConfigDict(strict=True)

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

# ─────────────────────────────────────────────────────────
# MODELOS INTERNOS (Salida — Sin strict, máxima flexibilidad)
# ─────────────────────────────────────────────────────────

class StopSchedule(BaseModel):
    destination_id: str
    suggested_arrival_min: Optional[int] = None
    earliest_arrival_min: Optional[int] = None
    latest_arrival_min: Optional[int] = None
    suggested_arrival_hhmm: Optional[str] = None

class RouteRequest(BaseModel):
    model_config = ConfigDict(strict=True)

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
    exposure_risk_nota: str = ""  # el riesgo de exposición va aparte y no suma a costo_total_ars
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

class EdgeRiskReport(BaseModel):
    """Reporte de riesgo de una arista individual."""
    edge_key: str
    prob_failure: float
    impact_mean: float
    geometry: List[List[float]] = []

class NetworkRiskReport(BaseModel):
    """Reporte consolidado de la red bayesiana post-Monte Carlo."""
    system_prob_failure: float
    system_impact_mean: float
    total_edges_evaluated: int
    monte_carlo_iterations: int
    convergence_reached: bool
    edges: List[EdgeRiskReport] = []
    executive_dictamen: List[str] = []

class RouteResponse(BaseModel):
    processing_time_ms: float
    total_edges: int
    toll_fallback_edges: int = 0
    pareto_solutions: List[ParetoResult]

class FleetRequest(BaseModel):
    model_config = ConfigDict(strict=True)

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
    # CISO Directive: Flag explícito de integridad para el cliente/frontend
    integrity_compromised: bool = Field(
        default=False,
        description=(
            "True si las rutas se calcularon sin inteligencia de riesgo "
            "debido a una violación de integridad en la cadena HMAC de los "
            "Priors bayesianos. El cliente debe tratar estas rutas como "
            "calculadas con priors conservadores por defecto."
        )
    )
    network_risk: Optional[NetworkRiskReport] = Field(
        default=None,
        description=(
            "Reporte de riesgo bayesiano de la red. Solo presente cuando "
            "stochastic_mode=True en la request."
        )
    )

# ─────────────────────────────────────────────────────────
# AUTH SCHEMAS (Fase 2 SGSI — A.9, A.10)
# ─────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    client_id: str = Field(..., min_length=1, max_length=128,
        description="Identificador único del cliente registrado.")
    client_secret: str = Field(..., min_length=8, max_length=256,
        description="Secreto del cliente (Base64-encoded).")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="TTL del access token en segundos.")
    refresh_token: str = Field(description="Token para renovar el access token.")

class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

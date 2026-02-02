# src/bloque1/models.py
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Literal, Type, TypeVar, Union, get_origin, get_args
import json
import logging

logger = logging.getLogger(__name__)
T = TypeVar('T', bound='SerializableMixin')

@dataclass(frozen=True)
class ErrorDefinition:
    message: str
    severity: Literal['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
    suggested_fix: str

ERROR_CATALOG: Dict[str, ErrorDefinition] = {
    "ERR_GEO_001": ErrorDefinition("Coordenadas fuera de rango.", "HIGH", "Validar Lat [-90, 90] y Lon [-180, 180]."),
    "ERR_TIME_001": ErrorDefinition("Cronología inválida.", "HIGH", "Asegurar que start < end."),
    "ERR_COST_001": ErrorDefinition("Perfil de costo inconsistente.", "CRITICAL", "Revisar tramos/parámetros."),
    "ERR_META_001": ErrorDefinition("Metadatos incompletos.", "MEDIUM", "Verificar source y version."),
    "ERR_SPEED_001": ErrorDefinition("Velocidad no positiva.", "HIGH", "Revisar que default > 0."),
    "ERR_ARC_001": ErrorDefinition("Error de topología.", "CRITICAL", "Evitar bucles (origin == destination).")
}

class PrimeLogisticsError(Exception):
    def __init__(self, context_msg: str, error_code: str):
        self.error_code = error_code
        self.definition = ERROR_CATALOG.get(error_code)
        self.severity = self.definition.severity if self.definition else "HIGH"
        self.suggested_fix = self.definition.suggested_fix if self.definition else ""
        msg = f"[{error_code}] {context_msg} -> {self.definition.message if self.definition else ''}"
        super().__init__(msg)

class SerializableMixin:
    def to_dict(self) -> Dict[str, Any]:
        def _serialize(obj):
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(i) for i in obj]
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj
        return _serialize(asdict(self))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls: Type[T], data: Optional[Dict[str, Any]]) -> Optional[T]:
        if data is None:
            return None

        annotations = getattr(cls, "__annotations__", {})
        processed: Dict[str, Any] = {}

        for key, value in data.items():
            if key not in annotations or value is None:
                processed[key] = value
                continue

            ftype = annotations[key]
            origin = get_origin(ftype)
            args = get_args(ftype)

            if origin is Union and type(None) in args:
                real_type = next(a for a in args if a is not type(None))
                if hasattr(real_type, "from_dict") and isinstance(value, dict):
                    processed[key] = real_type.from_dict(value)
                else:
                    processed[key] = value
                continue

            if origin is list:
                inner = args[0]
                if hasattr(inner, "from_dict") and isinstance(value, list):
                    processed[key] = [
                        inner.from_dict(i) if isinstance(i, dict) else i for i in value
                    ]
                else:
                    processed[key] = value
                continue

            if hasattr(ftype, "from_dict") and isinstance(value, dict):
                processed[key] = ftype.from_dict(value)
                continue

            if ftype is datetime and isinstance(value, str):
                processed[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                continue

            processed[key] = value

        return cls(**processed)

@dataclass(frozen=True)
class Metadata(SerializableMixin):
    source: Optional[str] = None
    version: Optional[str] = None
    timestamp: Optional[datetime] = field(default_factory=lambda: datetime.now(timezone.utc))
    extras: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "Metadata":
        if data is None:
            return cls()
        d = dict(data)
        source = d.pop("source", None)
        version = d.pop("version", None)
        timestamp = d.pop("timestamp", None)
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except Exception:
                timestamp = None
        extras = d
        return cls(source=source, version=version, timestamp=timestamp, extras=extras)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.source is not None:
            out["source"] = self.source
        if self.version is not None:
            out["version"] = self.version
        if self.timestamp is not None:
            out["timestamp"] = self.timestamp.isoformat()
        for k, v in self.extras.items():
            if k not in out:
                out[k] = v
        return out

@dataclass(frozen=True)
class Window(SerializableMixin):
    start: datetime
    end: datetime
    is_recurrent: bool = False

    def __post_init__(self):
        if self.start.tzinfo is None:
            logger.debug("Assuming UTC for naive Window.start")
            object.__setattr__(self, "start", self.start.replace(tzinfo=timezone.utc))
        if self.end.tzinfo is None:
            logger.debug("Assuming UTC for naive Window.end")
            object.__setattr__(self, "end", self.end.replace(tzinfo=timezone.utc))
        if self.start >= self.end:
            raise PrimeLogisticsError("start >= end", "ERR_TIME_001")

@dataclass(frozen=True)
class CostProfile(SerializableMixin):
    cost_type: Literal["flat", "bracket", "curve", "ref"]
    params: Dict[str, Any]

    def __post_init__(self):
        t = self.cost_type
        p = self.params or {}
        if t == "flat":
            if "variable_coef" not in p:
                raise PrimeLogisticsError("flat requires variable_coef", "ERR_COST_001")
            if not isinstance(p["variable_coef"], (int, float)):
                raise PrimeLogisticsError("variable_coef must be numeric", "ERR_COST_001")
        elif t == "bracket":
            tiers = p.get("tiers")
            if not isinstance(tiers, list) or not tiers:
                raise PrimeLogisticsError("bracket requires non-empty tiers", "ERR_COST_001")
            last_max = None
            for i, tier in enumerate(tiers):
                if not all(k in tier for k in ("min", "max", "price")):
                    raise PrimeLogisticsError(f"tier {i} missing keys", "ERR_COST_001")
                if not isinstance(tier["min"], (int, float)) or not isinstance(tier["max"], (int, float)):
                    raise PrimeLogisticsError(f"tier {i} min/max must be numeric", "ERR_COST_001")
                if tier["max"] < tier["min"]:
                    raise PrimeLogisticsError(f"tier {i} max < min", "ERR_COST_001")
                if tier["price"] < 0:
                    raise PrimeLogisticsError(f"tier {i} price < 0", "ERR_COST_001")
                if last_max is not None and tier["min"] != last_max:
                    raise PrimeLogisticsError(f"tier {i} gap/overlap detected", "ERR_COST_001")
                last_max = tier["max"]
        elif t == "curve":
            if "equation" not in p and "func_ref" not in p:
                raise PrimeLogisticsError("curve requires equation or func_ref", "ERR_COST_001")
        elif t == "ref":
            if "tariff_id" not in p:
                raise PrimeLogisticsError("ref requires tariff_id", "ERR_COST_001")

@dataclass(frozen=True)
class SpeedProfile(SerializableMixin):
    default: float
    conditional: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.default, (int, float)) or self.default <= 0:
            raise PrimeLogisticsError(f"default speed invalid: {self.default}", "ERR_SPEED_001")
        for k, v in self.conditional.items():
            if not isinstance(v, (int, float)) or v <= 0:
                raise PrimeLogisticsError(f"conditional speed invalid for {k}: {v}", "ERR_SPEED_001")

@dataclass(frozen=True)
class NodeRecord(SerializableMixin):
    id: str
    lat: float
    lon: float
    supply: float = 0.0
    demand: float = 0.0
    processing_cost: float = 0.0
    priority: int = 0
    metadata: Optional[Metadata] = None

    def __post_init__(self):
        if not (-90 <= self.lat <= 90) or not (-180 <= self.lon <= 180):
            raise PrimeLogisticsError(f"Coords ({self.lat}, {self.lon})", "ERR_GEO_001")
        if self.processing_cost < 0:
            raise PrimeLogisticsError(f"Costo de nodo negativo: {self.processing_cost}", "ERR_COST_001")

@dataclass(frozen=True)
class ArcRecord(SerializableMixin):
    id: str
    origin: str
    destination: str
    active: bool = True
    capacity: float = 10000.0
    cost_profile: Optional[CostProfile] = None
    speed_profile: Optional[SpeedProfile] = None
    windows: List[Window] = field(default_factory=list)
    metadata: Optional[Metadata] = None

    

    def __post_init__(self):
        if self.origin == self.destination:
            raise PrimeLogisticsError(f"Bucle en {self.id}", "ERR_ARC_001")

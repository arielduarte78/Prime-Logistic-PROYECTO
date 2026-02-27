# src/bloque1/validators.py
"""
Validadores atómicos y utilidades para el Bloque 1 (Entrada).
Diseñado para ser puro, sin estado, y fácil de testear.
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# ESTRUCTURAS DE RESULTADO
# ---------------------------------------------------------------------
@dataclass
class ValidationResult:
    """Objeto de transporte para resultados de validación."""
    ok: bool = True
    normalized: Optional[Any] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def add_error(self, code: str, message: str, field_name: str,
                  severity: str = "HIGH", suggested_fix: str = "") -> None:
        self.errors.append({
            "code": code,
            "message": message,
            "field": field_name,
            "severity": severity,
            "suggested_fix": suggested_fix
        })
        self.ok = False

# ---------------------------------------------------------------------
# VALIDADORES ATÓMICOS
# ---------------------------------------------------------------------
class NetworkValidator:
    """
    Laboratorio de validación pura.
    No mantiene estado. Solo recibe datos crudos y emite veredictos.
    """

    NODE_REGEX = re.compile(r"^NODE_[0-9]{4}$")
    ARC_REGEX = re.compile(r"^ARC_[0-9]{4}$")

    @staticmethod
    def validate_id(id_str: Any, kind: str) -> ValidationResult:
        """
        Verifica que los IDs cumplan el estándar estricto del proyecto.
        kind: 'NODE' o 'ARC'
        """
        res = ValidationResult()
        if kind not in ("NODE", "ARC"):
            res.add_error("ERR_ID_000", f"Kind inválido: {kind}", "kind", "HIGH", "Usar 'NODE' o 'ARC'")
            return res

        if not isinstance(id_str, str):
            res.add_error("ERR_ID_001", "ID debe ser string", "id", "HIGH", "Proveer ID como string")
            return res

        regex = NetworkValidator.NODE_REGEX if kind == "NODE" else NetworkValidator.ARC_REGEX
        if not regex.match(id_str):
            res.add_error(
                "ERR_ID_001",
                f"ID '{id_str}' no cumple formato {kind}.",
                "id",
                "HIGH",
                f"Usar formato {regex.pattern} (ej. {kind}_0001)"
            )
        else:
            res.normalized = id_str
        return res

    @staticmethod
    def validate_coordinate(lat: Any, lon: Any) -> ValidationResult:
        """Verifica límites geográficos físicos y tipos."""
        res = ValidationResult()
        # Latitud
        if lat is None:
            res.add_error("ERR_TYPE_001", "Latitud ausente", "lat", "HIGH", "Proveer latitud numérica")
        elif not isinstance(lat, (int, float)):
            res.add_error("ERR_TYPE_001", "Latitud debe ser numérica", "lat", "HIGH", "Usar int/float")
        elif not (-90 <= lat <= 90):
            res.add_error("ERR_GEO_001", f"Latitud {lat} fuera de rango", "lat", "HIGH", "Rango [-90, 90]")

        # Longitud
        if lon is None:
            res.add_error("ERR_TYPE_001", "Longitud ausente", "lon", "HIGH", "Proveer longitud numérica")
        elif not isinstance(lon, (int, float)):
            res.add_error("ERR_TYPE_001", "Longitud debe ser numérica", "lon", "HIGH", "Usar int/float")
        elif not (-180 <= lon <= 180):
            res.add_error("ERR_GEO_001", f"Longitud {lon} fuera de rango", "lon", "HIGH", "Rango [-180, 180]")

        if res.ok:
            res.normalized = {"lat": float(lat if lat is not None else 0.0), "lon": float(lon if lon is not None else 0.0)}
        return res

    @staticmethod
    def parse_iso8601(timestamp_s: Any) -> ValidationResult:
        """
        Intenta parsear una fecha ISO 8601 y normalizarla a UTC.
        Soporta 'Z' como sufijo. Devuelve ValidationResult.normalized = datetime (UTC).
        """
        res = ValidationResult()
        if not isinstance(timestamp_s, str):
            res.add_error("ERR_TIME_002", "Timestamp debe ser string ISO 8601", "timestamp", "MEDIUM", "Enviar string ISO 8601")
            return res

        try:
            clean_ts = timestamp_s.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_ts)
            if dt.tzinfo is None:
                # Política: asumimos UTC para timestamps naive; loggear para trazabilidad
                logger.debug("Assuming UTC for naive timestamp: %s", timestamp_s)
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            res.normalized = dt
        except Exception:
            res.add_error("ERR_TIME_002", f"Fecha '{timestamp_s}' inválida", "timestamp", "MEDIUM", "Usar YYYY-MM-DDTHH:MM:SSZ")
        return res

    @staticmethod
    def validate_window(start: Any, end: Any) -> ValidationResult:
        """
        start/end pueden ser str (ISO) o datetime. Devuelve datetime normalizados en UTC.
        """
        res = ValidationResult()
        # Parse/normalize start
        if isinstance(start, str):
            p = NetworkValidator.parse_iso8601(start)
            if not p.ok:
                return p
            start_dt = p.normalized
        elif isinstance(start, datetime):
            start_dt = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
        else:
            res.add_error("ERR_TIME_003", "Tipo de start inválido", "start", "MEDIUM", "Proveer ISO string o datetime")
            return res

        # Parse/normalize end
        if isinstance(end, str):
            p = NetworkValidator.parse_iso8601(end)
            if not p.ok:
                return p
            end_dt = p.normalized
        elif isinstance(end, datetime):
            end_dt = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        else:
            res.add_error("ERR_TIME_003", "Tipo de end inválido", "end", "MEDIUM", "Proveer ISO string o datetime")
            return res

        if start_dt is None or end_dt is None:
            res.add_error("ERR_TIME_003", "start o end no pudieron ser parseados", "window", "HIGH", "Proveer fechas válidas")
            return res
        if start_dt >= end_dt:
            res.add_error("ERR_TIME_001", f"start >= end ({start_dt} >= {end_dt})", "window", "HIGH", "Asegurar start < end")
            return res

        res.normalized = {"start": start_dt, "end": end_dt}
        return res

    @staticmethod
    def validate_cost_profile(cost_obj: Any) -> ValidationResult:
        """
        cost_obj: dict con 'cost_type' y 'params'. No instancia CostProfile aquí.
        """
        res = ValidationResult()
        if cost_obj is None:
            # cost_profile opcional; devolver ok con normalized None
            res.normalized = None
            return res

        if not isinstance(cost_obj, dict):
            res.add_error("ERR_COST_001", "Cost profile debe ser dict", "cost_profile", "CRITICAL", "Enviar cost_type y params")
            return res

        ctype = cost_obj.get("cost_type")
        params = cost_obj.get("params", {})

        if ctype not in ("flat", "bracket", "curve", "ref"):
            res.add_error("ERR_COST_001", f"Tipo inválido: {ctype}", "cost_type", "CRITICAL", "Usar flat|bracket|curve|ref")
            return res

        if ctype == "flat":
            if "variable_coef" not in params:
                res.add_error("ERR_COST_001", "Falta variable_coef para flat", "params.variable_coef", "CRITICAL", "Incluir variable_coef")
                return res
            if not isinstance(params["variable_coef"], (int, float)):
                res.add_error("ERR_COST_001", "variable_coef debe ser numérico", "params.variable_coef", "CRITICAL", "Usar número")
                return res

        elif ctype == "bracket":
            tiers = params.get("tiers")
            if not isinstance(tiers, list) or not tiers:
                res.add_error("ERR_COST_001", "Tiers inválidos o vacíos", "params.tiers", "CRITICAL", "Proveer lista de tiers ordenada")
                return res
            last_max = None
            for i, tier in enumerate(tiers):
                if not isinstance(tier, dict):
                    res.add_error("ERR_COST_001", f"Tier {i} debe ser dict", f"params.tiers[{i}]", "CRITICAL", "Cada tier: {min,max,price}")
                    return res
                if not all(k in tier for k in ("min", "max", "price")):
                    res.add_error("ERR_COST_001", f"Tier {i} incompleto", f"params.tiers[{i}]", "CRITICAL", "Incluir min,max,price")
                    return res
                if not isinstance(tier["min"], (int, float)) or not isinstance(tier["max"], (int, float)):
                    res.add_error("ERR_COST_001", f"Tier {i} min/max no numérico", f"params.tiers[{i}]", "CRITICAL", "min/max numéricos")
                    return res
                if tier["max"] < tier["min"]:
                    res.add_error("ERR_COST_001", f"Tier {i} max < min", f"params.tiers[{i}]", "CRITICAL", "Corregir min/max")
                    return res
                if tier["price"] < 0:
                    res.add_error("ERR_COST_001", f"Tier {i} price < 0", f"params.tiers[{i}]", "CRITICAL", "price >= 0")
                    return res
                if last_max is not None and tier["min"] != last_max:
                    res.add_error("ERR_COST_001", f"Tier {i} gap/overlap", f"params.tiers[{i}]", "CRITICAL", "Alinear min con previous max")
                    return res
                last_max = tier["max"]

        elif ctype == "curve":
            if "equation" not in params and "func_ref" not in params:
                res.add_error("ERR_COST_001", "curve requiere equation o func_ref", "params", "CRITICAL", "Incluir equation o func_ref")
                return res

        elif ctype == "ref":
            if "tariff_id" not in params:
                res.add_error("ERR_COST_001", "ref requiere tariff_id", "params.tariff_id", "CRITICAL", "Incluir tariff_id")
                return res

        res.normalized = {"cost_type": ctype, "params": params}
        return res

    @staticmethod
    def validate_speed_profile(speed_obj: Any) -> ValidationResult:
        """
        speed_obj: dict con 'default' y opcional 'conditional'.
        """
        res = ValidationResult()
        if speed_obj is None:
            res.normalized = None
            return res

        if not isinstance(speed_obj, dict):
            res.add_error("ERR_SPEED_001", "Speed profile debe ser dict", "speed_profile", "HIGH", "Enviar default y conditional opcional")
            return res

        default = speed_obj.get("default")
        if default is None or not isinstance(default, (int, float)) or default <= 0:
            res.add_error("ERR_SPEED_001", "default inválido", "speed_profile.default", "HIGH", "default > 0 (km/h)")

        cond = speed_obj.get("conditional", {})
        if not isinstance(cond, dict):
            res.add_error("ERR_SPEED_001", "conditional debe ser dict", "speed_profile.conditional", "MEDIUM", "Usar dict de condiciones")
        else:
            for k, v in cond.items():
                if not isinstance(v, (int, float)) or v <= 0:
                    res.add_error("ERR_SPEED_001", f"velocidad inválida para {k}: {v}", f"speed_profile.conditional.{k}", "HIGH", "velocidad > 0")

        if res.ok:
            res.normalized = {"default": float(default if default is not None else 0.0), "conditional": cond}
        return res

    @staticmethod
    def validate_arc_references(origin: Any, destination: Any, indexer) -> ValidationResult:
        """
        indexer debe exponer exists(id: str) -> bool
        """
        res = ValidationResult()
        if not isinstance(origin, str):
            res.add_error("ERR_REF_001", "Origin debe ser string", "origin", "CRITICAL", "Proveer origin ID")
        if not isinstance(destination, str):
            res.add_error("ERR_REF_001", "Destination debe ser string", "destination", "CRITICAL", "Proveer destination ID")
        if not res.ok:
            return res

        if not indexer.exists(origin):
            res.add_error("ERR_REF_001", f"Origen no existe: {origin}", "origin", "CRITICAL", "Cargar nodo origen primero")
        if not indexer.exists(destination):
            res.add_error("ERR_REF_001", f"Destino no existe: {destination}", "destination", "CRITICAL", "Cargar nodo destino primero")
        return res

    # -----------------------------------------------------------------
    # V1.3.5: Validadores para Discovery Engine
    # -----------------------------------------------------------------

    @staticmethod
    def validate_station_type(raw_type: Any, strict: bool = False) -> ValidationResult:
        """
        Valida y normaliza un station_type usando el mapeo canónico.

        Si strict=True, rechaza tipos desconocidos.
        Si strict=False, acepta tipos desconocidos pero emite warning.
        En ambos casos, normalized contendrá el valor canónico resultante.
        """
        from .station_normalizer import normalize_station_type, is_canonical

        res = ValidationResult()
        if raw_type is None or (isinstance(raw_type, str) and raw_type.strip() == ""):
            res.normalized = "warehouse"
            return res

        if not isinstance(raw_type, str):
            res.add_error(
                "ERR_STATION_TYPE",
                f"station_type debe ser string, recibido: {type(raw_type).__name__}",
                "station_type", "MEDIUM",
                "Proveer station_type como string"
            )
            return res

        try:
            canonical = normalize_station_type(raw_type, strict=strict)
            res.normalized = canonical
        except ValueError as exc:
            res.add_error(
                "ERR_STATION_TYPE",
                str(exc),
                "station_type", "MEDIUM",
                "Verificar mapeo canónico en station_normalizer."
            )
        return res

    @staticmethod
    def validate_fleet_record(data: Dict[str, Any]) -> ValidationResult:
        """
        Valida un registro completo de vehículo de flota (FLEET row).

        data debe contener:
          - mode: str ("truck", "car", "bus")
          - capacity: float > 0
          - cost_per_km: float > 0
          - max_range_km: float > 0
          - allowed_stations: List[str] (no vacía, valores canónicos)

        Retorna ValidationResult con normalized = dict limpio o errores.
        """
        res = ValidationResult()
        VALID_MODES = {"truck", "car", "bus"}

        # --- mode ---
        mode = data.get("mode")
        if not isinstance(mode, str):
            res.add_error(
                "ERR_FLEET_MODE",
                f"mode debe ser string, recibido: {type(mode).__name__}",
                "mode", "HIGH", f"Usar: {', '.join(sorted(VALID_MODES))}"
            )
        else:
            mode = mode.strip().lower()
            if mode not in VALID_MODES:
                res.add_error(
                    "ERR_FLEET_MODE",
                    f"mode '{mode}' inválido.",
                    "mode", "HIGH", f"Valores permitidos: {', '.join(sorted(VALID_MODES))}"
                )

        # --- capacity ---
        capacity = data.get("capacity")
        if capacity is None or not isinstance(capacity, (int, float)):
            res.add_error(
                "ERR_FLEET_CAPACITY",
                f"capacity debe ser numérico, recibido: {capacity}",
                "capacity", "HIGH", "Proveer número > 0"
            )
        elif capacity <= 0:
            res.add_error(
                "ERR_FLEET_CAPACITY",
                f"capacity debe ser > 0, recibido: {capacity}",
                "capacity", "HIGH", "Proveer número > 0"
            )

        # --- cost_per_km ---
        cost_per_km = data.get("cost_per_km")
        if cost_per_km is None or not isinstance(cost_per_km, (int, float)):
            res.add_error(
                "ERR_FLEET_COST",
                f"cost_per_km debe ser numérico, recibido: {cost_per_km}",
                "cost_per_km", "HIGH", "Proveer número > 0"
            )
        elif cost_per_km <= 0:
            res.add_error(
                "ERR_FLEET_COST",
                f"cost_per_km debe ser > 0, recibido: {cost_per_km}",
                "cost_per_km", "HIGH", "Proveer número > 0"
            )

        # --- max_range_km ---
        max_range_km = data.get("max_range_km")
        if max_range_km is None or not isinstance(max_range_km, (int, float)):
            res.add_error(
                "ERR_FLEET_RANGE",
                f"max_range_km debe ser numérico, recibido: {max_range_km}",
                "max_range_km", "HIGH", "Proveer número > 0"
            )
        elif max_range_km <= 0:
            res.add_error(
                "ERR_FLEET_RANGE",
                f"max_range_km debe ser > 0, recibido: {max_range_km}",
                "max_range_km", "HIGH", "Proveer número > 0"
            )

        # --- allowed_stations ---
        allowed = data.get("allowed_stations")
        if not isinstance(allowed, list) or len(allowed) == 0:
            res.add_error(
                "ERR_FLEET_STATIONS",
                "allowed_stations debe ser una lista no vacía de strings",
                "allowed_stations", "HIGH",
                "Proveer lista de tipos canónicos (e.g., ['warehouse', 'factory'])"
            )
        else:
            normalized_stations = []
            for i, s in enumerate(allowed):
                if not isinstance(s, str):
                    res.add_error(
                        "ERR_FLEET_STATIONS",
                        f"allowed_stations[{i}] debe ser string, recibido: {type(s).__name__}",
                        f"allowed_stations[{i}]", "HIGH", "Usar strings"
                    )
                else:
                    # Normalizar cada estación
                    st_res = NetworkValidator.validate_station_type(s, strict=False)
                    normalized_stations.append(st_res.normalized or s.strip().lower())
            if res.ok:
                allowed = normalized_stations

        # --- Construir resultado normalizado ---
        if res.ok:
            res.normalized = {
                "mode": mode.strip().lower() if isinstance(mode, str) else mode,
                "capacity": float(capacity if capacity is not None else 0.0),
                "cost_per_km": float(cost_per_km if cost_per_km is not None else 0.0),
                "max_range_km": float(max_range_km if max_range_km is not None else 0.0),
                "allowed_stations": allowed,
            }
            # Campos opcionales
            if "vehicle_id" in data:
                res.normalized["vehicle_id"] = str(data["vehicle_id"]).strip()
            if "count" in data:
                cnt = data["count"]
                if isinstance(cnt, int) and cnt >= 1:
                    res.normalized["count"] = cnt
                else:
                    res.normalized["count"] = 1

        return res

# ---------------------------------------------------------------------
# UTILIDAD PARA BATCH PRE-FILTER (RECOMENDADO PARA PERFORMANCE)
# ---------------------------------------------------------------------
def batch_validate_rows(rows: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    """
    Itera filas (dicts) y devuelve dicts con 'row' y 'result' (ValidationResult).
    Pensado para integrarse con pandas.read_csv(chunksize=...) o generadores.
    """
    for row in rows:
        result = ValidationResult()
        # ID y tipo (se espera que la fila tenga 'kind' indicando 'NODE' o 'ARC')
        kind = row.get("kind", "NODE")
        id_val = row.get("id")
        id_res = NetworkValidator.validate_id(id_val, kind)
        if not id_res.ok:
            result.ok = False
            result.errors.extend(id_res.errors)
            yield {"row": row, "result": result}
            continue
        # Coordenadas (si aplican)
        if "lat" in row or "lon" in row:
            lat = row.get("lat")
            lon = row.get("lon")
            geo_res = NetworkValidator.validate_coordinate(lat, lon)
            if not geo_res.ok:
                result.ok = False
                result.errors.extend(geo_res.errors)
                yield {"row": row, "result": result}
                continue
            if result.normalized is None:
                result.normalized = {}
            if geo_res.normalized is not None:
                result.normalized.update({"lat": geo_res.normalized["lat"], "lon": geo_res.normalized["lon"]})
        # Station type (Normalización Semántica)
        if "station_type" in row:
            st_res = NetworkValidator.validate_station_type(row.get("station_type"), strict=False)
            if not st_res.ok:
                result.ok = False
                result.errors.extend(st_res.errors)
                yield {"row": row, "result": result}
                continue
            if result.normalized is None:
                result.normalized = {}
            result.normalized["station_type"] = st_res.normalized
        # Cost profile
        if "cost_profile" in row:
            c_res = NetworkValidator.validate_cost_profile(row.get("cost_profile"))
            if not c_res.ok:
                result.ok = False
                result.errors.extend(c_res.errors)
                yield {"row": row, "result": result}
                continue
            if result.normalized is None:
                result.normalized = {}
            result.normalized["cost_profile"] = c_res.normalized

        # Speed profile
        if "speed_profile" in row:
            s_res = NetworkValidator.validate_speed_profile(row.get("speed_profile"))
            if not s_res.ok:
                result.ok = False
                result.errors.extend(s_res.errors)
                yield {"row": row, "result": result}
                continue
            if result.normalized is None:
                result.normalized = {}
            result.normalized["speed_profile"] = s_res.normalized

        # Windows (si vienen)
        if "windows" in row:
            windows = row.get("windows")
            if not isinstance(windows, list):
                result.add_error("ERR_TIME_004", "windows debe ser lista", "windows", "MEDIUM", "Enviar lista de ventanas")
                yield {"row": row, "result": result}
                continue
            normalized_windows = []
            for i, w in enumerate(windows):
                # w puede ser dict con 'start'/'end' strings
                if not isinstance(w, dict):
                    result.add_error("ERR_TIME_004", f"window[{i}] debe ser dict", f"windows[{i}]", "MEDIUM", "Enviar dict con start/end")
                    break
                w_res = NetworkValidator.validate_window(w.get("start"), w.get("end"))
                if not w_res.ok:
                    result.ok = False
                    result.errors.extend(w_res.errors)
                    break
                normalized_windows.append(w_res.normalized)
            if not result.ok:
                yield {"row": row, "result": result}
                continue
            if result.normalized is None:
                result.normalized = {}
            result.normalized["windows"] = normalized_windows

        yield {"row": row, "result": result}

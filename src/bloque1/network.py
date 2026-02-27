# src/bloque1/network.py
import copy
import logging
import threading
import traceback as _traceback
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Iterable, Tuple

from .models import NodeRecord, ArcRecord, PrimeLogisticsError, ERROR_CATALOG
from .validators import NetworkValidator, ValidationResult

logger = logging.getLogger(__name__)


class NetworkIndexer:
    def __init__(self) -> None:
        self._nodes: Dict[str, NodeRecord] = {}
        self._arcs: Dict[str, ArcRecord] = {}
        self._lock = threading.RLock()

    def get_all_node_ids(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(self._nodes.keys())

    def iter_nodes(self) -> Iterable[NodeRecord]:
        with self._lock:
            return list(self._nodes.values())

    def iter_arcs(self) -> Iterable[ArcRecord]:
        with self._lock:
            return list(self._arcs.values())

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "nodes": {k: v.to_dict() for k, v in self._nodes.items()},
                "arcs": {k: v.to_dict() for k, v in self._arcs.items()},
            }

    def clear_indexer(self) -> None:
        with self._lock:
            self._nodes.clear()
            self._arcs.clear()

    def exists_node(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self._nodes

    def exists_arc(self, arc_id: str) -> bool:
        with self._lock:
            return arc_id in self._arcs

    def exists(self, entity_id: str) -> bool:
        with self._lock:
            return (entity_id in self._nodes) or (entity_id in self._arcs)

    def get_node(self, node_id: str) -> Optional[NodeRecord]:
        with self._lock:
            return self._nodes.get(node_id)

    def get_arc(self, arc_id: str) -> Optional[ArcRecord]:
        with self._lock:
            return self._arcs.get(arc_id)

    def register_node(self, node: NodeRecord) -> None:
        with self._lock:
            existing = self._nodes.get(node.id)
            if existing:
                ev = existing.metadata.version if existing.metadata else None
                nv = node.metadata.version if node.metadata else None
                if ev is not None and nv is not None and ev == nv:
                    logger.info("Node %s ya registrado con misma versión %s; ignorando", node.id, ev)
                    return
                logger.warning("Actualizando nodo %s: %s -> %s", node.id, ev, nv)
            self._nodes[node.id] = node
            logger.debug("Node registrado: %s", node.id)

    def register_arc(self, arc: ArcRecord) -> None:
        with self._lock:
            existing = self._arcs.get(arc.id)
            if existing:
                ev = existing.metadata.version if existing.metadata else None
                nv = arc.metadata.version if arc.metadata else None
                if ev is not None and nv is not None and ev == nv:
                    logger.info("Arc %s ya registrado con misma versión %s; ignorando", arc.id, ev)
                    return
                logger.warning("Actualizando arco %s: %s -> %s", arc.id, ev, nv)
            self._arcs[arc.id] = arc
            logger.debug("Arc registrado: %s", arc.id)

    def register_discovered_arc(self, arc: ArcRecord) -> None:
        """
        Registra un arco descubierto por el DiscoveryEngine.
        Bypass directo: no pasa por las validaciones de Ingestor
        ya que el DiscoveryEngine ya lo validó (Filtros 1/2/3).
        """
        with self._lock:
            self._arcs[arc.id] = arc
            logger.debug("Arc descubierto registrado: %s (%s -> %s)",
                         arc.id, arc.origin, arc.destination)

    @property
    def node_count(self) -> int:
        with self._lock:
            return len(self._nodes)

    @property
    def arc_count(self) -> int:
        with self._lock:
            return len(self._arcs)


class Ingestor:
    def __init__(self, indexer: NetworkIndexer) -> None:
        self.indexer = indexer
        self._errors_lock = threading.RLock()
        self._errors: List[Dict[str, Any]] = []

    def _log_errors(self, result: ValidationResult, context: str) -> None:
        for err in result.errors:
            e = copy.deepcopy(err)
            e["context"] = context
            e["timestamp"] = datetime.now(timezone.utc).isoformat()
            with self._errors_lock:
                self._errors.append(e)
            logger.debug("Validation error logged: %s", e)

    def _add_system_error(self, msg: str, code: str, context: Optional[str] = None, include_traceback: bool = False) -> None:
        definition = ERROR_CATALOG.get(code)
        entry: Dict[str, Any] = {
            "code": code,
            "message": msg,
            "severity": getattr(definition, "severity", "CRITICAL") if definition else "CRITICAL",
            "context": context,
            "suggested_fix": getattr(definition, "suggested_fix", "") if definition else "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if include_traceback:
            entry["traceback"] = _traceback.format_exc()
        with self._errors_lock:
            self._errors.append(entry)
        logger.error("System error: %s", entry)

    def get_errors(self) -> List[Dict[str, Any]]:
        with self._errors_lock:
            return list(self._errors)

    def clear_errors(self) -> None:
        with self._errors_lock:
            self._errors.clear()

    def load_node(self, raw_data: Dict[str, Any]) -> bool:
        if not isinstance(raw_data, dict):
            self._add_system_error("raw_data debe ser dict", "ERR_SYS_001", context="load_node")
            return False

        id_val = raw_data.get("id")
        if id_val is None:
            self._add_system_error("id ausente en raw_data", "ERR_ID_002", context="load_node")
            return False

        id_res = NetworkValidator.validate_id(id_val, kind="NODE")
        if not id_res.ok:
            self._log_errors(id_res, context=f"Node {id_val}")
            return False

        geo_res = NetworkValidator.validate_coordinate(raw_data.get("lat"), raw_data.get("lon"))
        if not geo_res.ok:
            self._log_errors(geo_res, context=f"Node {id_val}")
            return False

        try:
            node = NodeRecord.from_dict(raw_data)
            if node is None:
                self._add_system_error(f"Node {id_val} instanciado como None", "ERR_MODEL_INIT", context=f"Node {id_val}")
                return False
            self.indexer.register_node(node)
            logger.info("Node cargado: %s", node.id)
            return True

        except PrimeLogisticsError as ple:
            code = getattr(ple, "error_code", "ERR_MODEL_INIT")
            self._add_system_error(str(ple), code, context=f"Node {id_val}")
            return False
        except Exception as e:
            self._add_system_error(f"Error instanciando Node {id_val}: {e}", "ERR_MODEL_INIT", context=f"Node {id_val}", include_traceback=True)
            logger.exception("Unexpected error instantiating Node %s", id_val)
            return False

    def load_arc(self, raw_data: Dict[str, Any]) -> bool:
        if not isinstance(raw_data, dict):
            self._add_system_error("raw_data debe ser dict", "ERR_SYS_001", context="load_arc")
            return False

        id_val = raw_data.get("id")
        if id_val is None:
            self._add_system_error("id ausente en raw_data", "ERR_ID_002", context="load_arc")
            return False

        id_res = NetworkValidator.validate_id(id_val, kind="ARC")
        if not id_res.ok:
            self._log_errors(id_res, context=f"Arc {id_val}")
            return False

        origin = raw_data.get("origin")
        destination = raw_data.get("destination")

        # Type Guard: origin y destination deben ser str
        if not isinstance(origin, str) or not isinstance(destination, str):
            self._add_system_error(
                f"Arc {id_val}: origin/destination deben ser str, recibido "
                f"origin={type(origin).__name__}, destination={type(destination).__name__}",
                "ERR_ID_002", context=f"Arc {id_val}"
            )
            return False

        ref_res = NetworkValidator.validate_arc_references(origin, destination, self.indexer)
        if not ref_res.ok:
            self._log_errors(ref_res, context=f"Arc {id_val}")
            return False

        if "cost_profile" in raw_data:
            c_res = NetworkValidator.validate_cost_profile(raw_data.get("cost_profile"))
            if not c_res.ok:
                self._log_errors(c_res, context=f"Arc {id_val}")
                return False

        if "speed_profile" in raw_data:
            s_res = NetworkValidator.validate_speed_profile(raw_data.get("speed_profile"))
            if not s_res.ok:
                self._log_errors(s_res, context=f"Arc {id_val}")
                return False

        if "windows" in raw_data:
            windows = raw_data.get("windows")
            if not isinstance(windows, list):
                self._add_system_error("windows debe ser lista", "ERR_TIME_004", context=f"Arc {id_val}")
                return False
            for i, w in enumerate(windows):
                w_res = NetworkValidator.validate_window(w.get("start"), w.get("end"))
                if not w_res.ok:
                    self._log_errors(w_res, context=f"Arc {id_val} windows[{i}]")
                    return False

        try:
            arc = ArcRecord.from_dict(raw_data)
            if arc is None:
                self._add_system_error(f"Arc {id_val} instanciado como None", "ERR_MODEL_INIT", context=f"Arc {id_val}")
                return False

            md = getattr(arc, "metadata", None)
            mode = None
            station_origin = None
            station_dest = None
            cap_val = None
            cap_unit = None

            if isinstance(md, dict):
                mode = md.get("mode") or md.get("transport_type") or md.get("transport_mode")
                cap_val = md.get("capacity", None)
                cap_unit = md.get("capacity_unit", None)
            else:
                extras = getattr(md, "extras", None)
                if isinstance(extras, dict):
                    mode = extras.get("mode") or extras.get("transport_type") or extras.get("transport_mode")
                    cap_val = extras.get("capacity", None)
                    cap_unit = extras.get("capacity_unit", None)
                else:
                    mode = getattr(md, "mode", None)
                    cap_val = getattr(md, "capacity", None)
                    cap_unit = getattr(md, "capacity_unit", None)

            origin_node = self.indexer.get_node(origin)
            dest_node = self.indexer.get_node(destination)
            if origin_node:
                try:
                    o_md = getattr(origin_node, "metadata", None)
                    if isinstance(o_md, dict):
                        station_origin = o_md.get("station_type")
                    else:
                        o_ex = getattr(o_md, "extras", None)
                        if isinstance(o_ex, dict):
                            station_origin = o_ex.get("station_type")
                        else:
                            station_origin = getattr(o_md, "station_type", None)
                except Exception:
                    station_origin = None
            if dest_node:
                try:
                    d_md = getattr(dest_node, "metadata", None)
                    if isinstance(d_md, dict):
                        station_dest = d_md.get("station_type")
                    else:
                        d_ex = getattr(d_md, "extras", None)
                        if isinstance(d_ex, dict):
                            station_dest = d_ex.get("station_type")
                        else:
                            station_dest = getattr(d_md, "station_type", None)
                except Exception:
                    station_dest = None

            if mode:
                from .config import MODE_ALLOWED_STATION_TYPES
                mode_key = str(mode).strip().lower()
                allowed = MODE_ALLOWED_STATION_TYPES.get(mode_key, MODE_ALLOWED_STATION_TYPES.get("default", ()))
                def _is_allowed(st):
                    if st is None:
                        return False
                    return str(st).strip().lower() in {a.lower() for a in allowed}
                if not _is_allowed(station_origin) or not _is_allowed(station_dest):
                    self._add_system_error(
                        f"Arc {id_val} modo '{mode}' incompatible con estaciones: origin='{station_origin}' dest='{station_dest}'",
                        "ERR_MODE_STATION_INCOMPAT",
                        context=f"Arc {id_val}"
                    )
                    return False

            if cap_val is not None:
                try:
                    cap_f = float(cap_val)
                except Exception:
                    self._add_system_error(f"Arc {id_val} capacity inválida: {cap_val}", "ERR_CAP_INVALID", context=f"Arc {id_val}")
                    return False

                if cap_unit:
                    from .config import UNIT_CONVERSIONS_TO_TON
                    conv = UNIT_CONVERSIONS_TO_TON.get(str(cap_unit).lower())
                    if conv is not None:
                        cap_f = cap_f * float(conv)
                    else:
                        logger.warning("Arc %s capacity_unit desconocida '%s'; se asume toneladas", id_val, cap_unit)

                if cap_f < 0:
                    self._add_system_error(f"Arc {id_val} tiene capacity negativa: {cap_f}", "ERR_CAP_NEG", context=f"Arc {id_val}")
                    return False

                from .config import MAX_CAPACITY
                if cap_f > MAX_CAPACITY:
                    self._add_system_error(
                        f"Arc {id_val} capacity {cap_f} excede MAX_CAPACITY global {MAX_CAPACITY}",
                        "ERR_CAP_TOO_LARGE",
                        context=f"Arc {id_val}"
                    )
                    return False

            self.indexer.register_arc(arc)

            if cap_val is not None and mode:
                try:
                    cap_f = float(cap_val)
                    from .config import MODE_MAX_CAPACITY, UNIT_CONVERSIONS_TO_TON
                    if cap_unit:
                        conv = UNIT_CONVERSIONS_TO_TON.get(str(cap_unit).lower())
                        if conv is not None:
                            cap_f = cap_f * float(conv)
                    mode_key = str(mode).strip().lower()
                    threshold = MODE_MAX_CAPACITY.get(mode_key, MODE_MAX_CAPACITY.get("default"))
                    if threshold is not None and cap_f > threshold:
                        msg = f"Arc {id_val} capacity {cap_f} t excede umbral por modo {mode_key} ({threshold} t); se clampa en export_matrices"
                        self._add_system_error(msg, "WARN_CAP_EXCEEDS_MODE", context=f"Arc {id_val}")
                        logger.warning(msg)
                except Exception:
                    pass

            logger.info("Arc cargado: %s", arc.id)
            return True

        except PrimeLogisticsError as ple:
            code = getattr(ple, "error_code", "ERR_MODEL_INIT")
            self._add_system_error(str(ple), code, context=f"Arc {id_val}")
            return False
        except Exception as e:
            self._add_system_error(f"Error instanciando Arc {id_val}: {e}", "ERR_MODEL_INIT", context=f"Arc {id_val}", include_traceback=True)
            logger.exception("Unexpected error instantiating Arc %s", id_val)
            return False

    def load_nodes(self, rows: Iterable[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
        success = 0
        failed = 0
        failed_rows: List[Dict[str, Any]] = []
        for row in rows:
            if self.load_node(row):
                success += 1
            else:
                failed += 1
                failed_rows.append(row)
        logger.info("Batch nodes processed: success=%d failed=%d", success, failed)
        return success, failed, failed_rows

    def load_arcs(self, rows: Iterable[Dict[str, Any]]) -> Tuple[int, int, List[Dict[str, Any]]]:
        success = 0
        failed = 0
        failed_rows: List[Dict[str, Any]] = []
        for row in rows:
            if self.load_arc(row):
                success += 1
            else:
                failed += 1
                failed_rows.append(row)
        logger.info("Batch arcs processed: success=%d failed=%d", success, failed)
        return success, failed, failed_rows

    def get_validation_report(self) -> Dict[str, Any]:
        with self._errors_lock:
            return {
                "node_count": self.indexer.node_count,
                "arc_count": self.indexer.arc_count,
                "errors": list(self._errors),
                "error_count": len(self._errors),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

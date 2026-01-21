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

# -----------------------------------------------------------------------------
# REGISTRO ÚNICO DE VERDAD (INDEXER)
# -----------------------------------------------------------------------------
class NetworkIndexer:
    """
    Mantiene el inventario de entidades cargadas en memoria.
    Garantiza unicidad de IDs y acceso O(1).
    Thread-safe para operaciones básicas de registro/consulta.
    """
    def __init__(self) -> None:
        self._nodes: Dict[str, NodeRecord] = {}
        self._arcs: Dict[str, ArcRecord] = {}
        self._lock = threading.RLock()

    # --- consultas específicas (thread-safe) ---
    def exists_node(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self._nodes

    def exists_arc(self, arc_id: str) -> bool:
        with self._lock:
            return arc_id in self._arcs

    def exists(self, entity_id: str) -> bool:
        with self._lock:
            return (entity_id in self._nodes) or (entity_id in self._arcs)

    # --- getters ---
    def get_node(self, node_id: str) -> Optional[NodeRecord]:
        with self._lock:
            return self._nodes.get(node_id)

    def get_arc(self, arc_id: str) -> Optional[ArcRecord]:
        with self._lock:
            return self._arcs.get(arc_id)

    # --- registro con política de versionado simple ---
    def register_node(self, node: NodeRecord) -> None:
        with self._lock:
            existing = self._nodes.get(node.id)
            if existing:
                # Manejo seguro de metadata None
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

    @property
    def node_count(self) -> int:
        with self._lock:
            return len(self._nodes)

    @property
    def arc_count(self) -> int:
        with self._lock:
            return len(self._arcs)

# -----------------------------------------------------------------------------
# INGESTOR: COORDINA VALIDACIÓN, INSTANCIACIÓN Y REGISTRO
# -----------------------------------------------------------------------------
class Ingestor:
    """
    Coordina la validación y creación de objetos.
    Fase 1: Validación Estática (Regex, Tipos).
    Fase 2: Instanciación (Dataclasses).
    Fase 3: Registro (Indexer).
    """

    def __init__(self, indexer: NetworkIndexer) -> None:
        self.indexer = indexer
        self._errors_lock = threading.RLock()
        self.errors: List[Dict[str, Any]] = []

    # -------------------------
    # Helpers internos
    # -------------------------
    def _log_errors(self, result: ValidationResult, context: str) -> None:
        """
        Añade errores al acumulador sin mutar el ValidationResult original.
        """
        for err in result.errors:
            e = copy.deepcopy(err)
            e["context"] = context
            e["timestamp"] = datetime.now(timezone.utc).isoformat()
            with self._errors_lock:
                self.errors.append(e)
            logger.debug("Validation error logged: %s", e)

    def _add_system_error(self, msg: str, code: str, context: Optional[str] = None, include_traceback: bool = False) -> None:
        """
        Añade un error de sistema con metadatos homogéneos.
        """
        definition = ERROR_CATALOG.get(code)
        entry: Dict[str, Any] = {
            "code": code,
            "message": msg,
            "severity": getattr(definition, "severity", "CRITICAL") if definition else "CRITICAL",
            "context": context,
            "suggested_fix": getattr(definition, "suggested_fix", "") if definition else "",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if include_traceback:
            entry["traceback"] = _traceback.format_exc()
        with self._errors_lock:
            self.errors.append(entry)
        logger.error("System error: %s", entry)

    # -------------------------
    # Carga de nodos
    # -------------------------
    def load_node(self, raw_data: Dict[str, Any]) -> bool:
        """
        Intenta cargar un nodo desde un diccionario crudo.
        Retorna True si fue exitoso, False si hubo errores.
        """
        if not isinstance(raw_data, dict):
            self._add_system_error("raw_data debe ser dict", "ERR_SYS_001", context="load_node")
            return False

        id_val = raw_data.get("id")
        if id_val is None:
            logger.warning("load_node: id ausente en raw_data")
        # 1. Validación Estática de ID
        id_res = NetworkValidator.validate_id(id_val, kind="NODE")
        if not id_res.ok:
            self._log_errors(id_res, context=f"Node {id_val}")
            return False

        # 2. Validación Estática de Coordenadas
        geo_res = NetworkValidator.validate_coordinate(raw_data.get("lat"), raw_data.get("lon"))
        if not geo_res.ok:
            self._log_errors(geo_res, context=f"Node {id_val}")
            return False

        # 3. Instanciación blindada
        try:
            node = NodeRecord.from_dict(raw_data)
            if node is None:
                self._add_system_error(f"Node {id_val} instanciado como None", "ERR_MODEL_INIT", context=f"Node {id_val}")
                return False

            # 4. Registro
            self.indexer.register_node(node)
            logger.info("Node cargado: %s", node.id)
            return True

        except PrimeLogisticsError as ple:
            # errores esperados de validación/modelo
            code = getattr(ple, "error_code", "ERR_MODEL_INIT")
            self._add_system_error(str(ple), code, context=f"Node {id_val}")
            return False
        except Exception as e:
            # errores inesperados
            self._add_system_error(f"Error instanciando Node {id_val}: {e}", "ERR_MODEL_INIT", context=f"Node {id_val}", include_traceback=True)
            logger.exception("Unexpected error instantiating Node %s", id_val)
            return False

    # -------------------------
    # Carga de arcos
    # -------------------------
    def load_arc(self, raw_data: Dict[str, Any]) -> bool:
        """
        Carga un arco. Requiere que los nodos origen/destino ya existan.
        """
        if not isinstance(raw_data, dict):
            self._add_system_error("raw_data debe ser dict", "ERR_SYS_001", context="load_arc")
            return False

        id_val = raw_data.get("id")
        if id_val is None:
            logger.warning("load_arc: id ausente en raw_data")

        # 1. Validación de ID
        id_res = NetworkValidator.validate_id(id_val, kind="ARC")
        if not id_res.ok:
            self._log_errors(id_res, context=f"Arc {id_val}")
            return False

        # 2. Validación de Referencias (usar exists_node para mayor claridad)
        origin = raw_data.get("origin")
        destination = raw_data.get("destination")
        ref_res = NetworkValidator.validate_arc_references(origin, destination, self.indexer)
        if not ref_res.ok:
            self._log_errors(ref_res, context=f"Arc {id_val}")
            return False

        # 3. Validaciones de Perfiles (Fail Fast)
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

        # 4. Instanciación
        try:
            arc = ArcRecord.from_dict(raw_data)
            if arc is None:
                self._add_system_error(f"Arc {id_val} instanciado como None", "ERR_MODEL_INIT", context=f"Arc {id_val}")
                return False
            self.indexer.register_arc(arc)
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

    # -------------------------
    # Batch loaders
    # -------------------------
    def load_nodes(self, rows: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Procesa múltiples filas de nodos. Devuelve (success_count, failed_count).
        """
        success = 0
        failed = 0
        for row in rows:
            if self.load_node(row):
                success += 1
            else:
                failed += 1
        logger.info("Batch nodes processed: success=%d failed=%d", success, failed)
        return success, failed

    def load_arcs(self, rows: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Procesa múltiples filas de arcos. Devuelve (success_count, failed_count).
        """
        success = 0
        failed = 0
        for row in rows:
            if self.load_arc(row):
                success += 1
            else:
                failed += 1
        logger.info("Batch arcs processed: success=%d failed=%d", success, failed)
        return success, failed

    # -------------------------
    # Reportes y utilidades
    # -------------------------
    def get_validation_report(self) -> Dict[str, Any]:
        with self._errors_lock:
            return {
                "node_count": self.indexer.node_count,
                "arc_count": self.indexer.arc_count,
                "errors": list(self.errors),
                "error_count": len(self.errors),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }

    def clear_errors(self) -> None:
        with self._errors_lock:
            self.errors.clear()


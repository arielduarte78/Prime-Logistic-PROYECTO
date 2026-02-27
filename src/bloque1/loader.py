# loader.py — Cargador V1.3.5 (NODES + FLEET, sin ARCS manuales)
"""
Cargador optimizado para Excel/Parquet.
V1.3.5: Elimina la lectura de ARCS (ahora descubiertos por DiscoveryEngine)
         y agrega lectura del tab FLEET con validacion via validate_fleet_record.
"""
from __future__ import annotations

import json
import logging
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Tuple

from .models import NodeRecord
from .fleet_schema import FleetVehicle
from .validators import NetworkValidator

logger = logging.getLogger(__name__)


class ExcelLoader:
    """
    Cargador Hibrido de Alto Rendimiento V1.3.5.
    Detecta automaticamente si existe un cache en Parquet para acelerar la carga.
    Retorna (nodes, fleet) — ya no carga ARCS manuales.
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"CRITICAL: No existe el archivo {self.file_path}")

    @staticmethod
    def _safe_json_parse(val: Any) -> Dict[str, Any]:
        """Parsea JSON de forma segura y rapida."""
        if val is None or val == "" or pd.isna(val):
            return {}
        if isinstance(val, dict):
            return val
        try:
            return json.loads(str(val))
        except json.JSONDecodeError:
            logger.warning("Metadata corrupta ignorada: %s", val)
            return {}

    # ------------------------------------------------------------------
    # Metodo principal
    # ------------------------------------------------------------------
    def run(self) -> Tuple[List[NodeRecord], List[FleetVehicle]]:
        """
        Carga el archivo Excel/Parquet y retorna (nodes, fleet).
        Ya NO carga arcos; estos seran descubiertos por DiscoveryEngine.
        """
        # --- detectar parquet cache ---
        path_str = str(self.file_path)
        parquet_nodes = Path(path_str.replace(".xlsx", "_nodes.parquet"))

        if parquet_nodes.exists():
            logger.info("Usando Cache Parquet (Ultra Rapido): %s", parquet_nodes.name)
            try:
                df_nodes = pd.read_parquet(parquet_nodes)
                source_tag = "Parquet Cache"
            except Exception as e:
                logger.warning("Fallo al leer Parquet, reintentando con Excel... %s", e)
                df_nodes, source_tag = self._read_nodes_from_excel()
        else:
            logger.info("Iniciando Ingesta desde Excel: %s", self.file_path.name)
            df_nodes, source_tag = self._read_nodes_from_excel()

        # --- FASE 1: NODOS ---
        nodes = self._parse_nodes(df_nodes, source_tag)

        # --- FASE 2: FLEET (nuevo V1.3.5) ---
        fleet = self._parse_fleet()

        logger.info(
            "Carga V1.3.5 finalizada: %d nodos, %d vehiculos de flota.",
            len(nodes), len(fleet),
        )
        return nodes, fleet

    # ------------------------------------------------------------------
    # Parsing de nodos
    # ------------------------------------------------------------------
    def _parse_nodes(self, df_nodes: pd.DataFrame, source_tag: str) -> List[NodeRecord]:
        raw_data = df_nodes.to_dict("records")
        logger.info("Procesando %d nodos...", len(raw_data))
        nodes: List[NodeRecord] = []

        for row in raw_data:
            if row.get("id") is None or bool(pd.isna(row.get("id"))):
                continue

            # V1.3.5: Usar el validador canónico estricto de la Fase 1
            raw_station = row.get("station_type")
            st_res = NetworkValidator.validate_station_type(raw_station, strict=False)
            station_type = st_res.normalized if st_res.normalized else "warehouse"

            try:
                node = NodeRecord(
                    id=str(row["id"]).strip(),
                    lat=float(row.get("lat") or 0.0),
                    lon=float(row.get("lon") or 0.0),
                    station_type=station_type,
                    supply=float(row.get("supply") or 0.0) if row.get("supply") is not None and not bool(pd.isna(row.get("supply"))) else 0.0,
                    demand=float(row.get("demand") or 0.0) if row.get("demand") is not None and not bool(pd.isna(row.get("demand"))) else 0.0,
                    processing_cost=float(row.get("proc_cost") or 0.0) if row.get("proc_cost") is not None and not bool(pd.isna(row.get("proc_cost"))) else 0.0,
                )
                nodes.append(node)
            except Exception as e:
                logger.warning("Nodo '%s' descartado por error: %s", row.get("id"), e)

        return nodes

    # ------------------------------------------------------------------
    # Parsing de flota (V1.3.5)
    # ------------------------------------------------------------------
    def _parse_fleet(self) -> List[FleetVehicle]:
        """Lee el tab FLEET del Excel y valida cada registro."""
        try:
            df_fleet = pd.read_excel(
                self.file_path,
                sheet_name="FLEET",
                dtype={"vehicle_id": str, "mode": str, "allowed_stations": str},
            )
        except Exception as e:
            logger.error("No se pudo leer la hoja FLEET: %s", e)
            return []

        raw_data = df_fleet.to_dict("records")
        logger.info("Procesando %d vehiculos de flota...", len(raw_data))
        vehicles: List[FleetVehicle] = []

        for i, row in enumerate(raw_data):
            # Parsear allowed_stations de string CSV a lista
            raw_stations = row.get("allowed_stations", "")
            if isinstance(raw_stations, str) and raw_stations.strip():
                allowed_list = [s.strip().lower() for s in raw_stations.split(",") if s.strip()]
            else:
                allowed_list = []

            payload = {
                "mode": row.get("mode"),
                "capacity": row.get("capacity"),
                "cost_per_km": row.get("cost_per_km"),
                "max_range_km": row.get("max_range_km"),
                "allowed_stations": allowed_list,
            }
            # Campos opcionales
            if row.get("vehicle_id") is not None and not bool(pd.isna(row.get("vehicle_id", None))):
                payload["vehicle_id"] = str(row["vehicle_id"]).strip()
            if row.get("count") is not None and not bool(pd.isna(row.get("count", None))):
                payload["count"] = int(row["count"])

            # Validar con el validador de Phase 1
            result = NetworkValidator.validate_fleet_record(payload)
            if not result.ok:
                for err in result.errors:
                    logger.warning("FLEET fila %d rechazada [%s]: %s", i, err.get("code"), err.get("msg"))
                continue

            try:
                normalized = result.normalized if result.normalized is not None else {}
                vehicle = FleetVehicle(**normalized)  # type: ignore[arg-type]
                vehicles.append(vehicle)
                logger.debug("Vehiculo cargado: %s (%s)", vehicle.vehicle_id or f"fleet_{i}", vehicle.mode)
            except Exception as e:
                logger.warning("FLEET fila %d: error instanciando FleetVehicle: %s", i, e)

        return vehicles

    # ------------------------------------------------------------------
    # Lectura interna desde Excel
    # ------------------------------------------------------------------
    def _read_nodes_from_excel(self) -> Tuple[pd.DataFrame, str]:
        """Lee la hoja NODES del Excel original."""
        df_nodes = pd.read_excel(
            self.file_path,
            sheet_name="NODES",
            dtype={"id": str, "station_type": str},
        )
        return df_nodes, "Excel Fast Loader"
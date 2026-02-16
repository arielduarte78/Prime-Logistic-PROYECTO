# loader.py: cargador optimizado para Excel/Parquet con Pandas.
import json
import logging
import pandas as pd
from pathlib import Path
from typing import Dict, Any

# Importamos el Ingestor 
from .network import Ingestor

logger = logging.getLogger(__name__)

class ExcelLoader:
    """
    Cargador Híbrido de Alto Rendimiento.
    Detecta automáticamente si existe un caché en Parquet para acelerar la carga.
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"CRITICAL: No existe el archivo {self.file_path}")

    def _safe_json_parse(self, val: Any) -> Dict[str, Any]:
        """Parsea JSON de forma segura y rápida."""
        if val is None or val == "" or pd.isna(val):
            return {}
        if isinstance(val, dict):
            return val
        try:
            return json.loads(str(val))
        except json.JSONDecodeError:
            logger.warning(f"Metadata corrupta ignorada: {val}")
            return {}

    def run(self, ingestor: Ingestor) -> None:
        # Definimos las rutas de caché posibles
        path_str = str(self.file_path)
        parquet_nodes = Path(path_str.replace(".xlsx", "_nodes.parquet"))
        parquet_arcs = Path(path_str.replace(".xlsx", "_arcs.parquet"))

        # ESTRATEGIA DE CARGA: ¿Parquet o Excel?
        if parquet_nodes.exists() and parquet_arcs.exists():
            logger.info(f"⚡ Usando Caché Parquet (Ultra Rápido): {parquet_nodes.name}")
            try:
                df_nodes = pd.read_parquet(parquet_nodes)
                df_arcs = pd.read_parquet(parquet_arcs)
                source_tag = "Parquet Cache"
            except Exception as e:
                logger.warning(f"Fallo al leer Parquet, reintentando con Excel... {e}")
                df_nodes, df_arcs, source_tag = self._read_from_excel()
        else:
            logger.info(f"🚀 Iniciando Ingesta desde Excel: {self.file_path.name}")
            df_nodes, df_arcs, source_tag = self._read_from_excel()

        # --- FASE 1: NODOS ---
        raw_nodes_data = df_nodes.to_dict('records')
        logger.info(f"Procesando {len(raw_nodes_data)} nodos...")
        clean_nodes = []

        for row in raw_nodes_data:
            if pd.isna(row.get("id")): 
                continue

            node_payload = {
                "id": str(row["id"]).strip(),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "supply": float(row.get("supply") or 0.0) if not pd.isna(row.get("supply")) else 0.0,
                "demand": float(row.get("demand") or 0.0) if not pd.isna(row.get("demand")) else 0.0,
                "processing_cost": float(row.get("proc_cost") or 0.0) if not pd.isna(row.get("proc_cost")) else 0.0,
                "metadata": {
                    "station_type": str(row.get("station_type", "warehouse")).strip().lower(),
                    "source": source_tag
                }
            }
            clean_nodes.append(node_payload)

        ingestor.load_nodes(clean_nodes)

        # --- FASE 2: ARCOS (MULTI-MODAL) ---
        raw_arcs_data = df_arcs.to_dict('records')
        logger.info(f"Procesando {len(raw_arcs_data)} arcos...")
        clean_arcs = []

        for row in raw_arcs_data:
            if pd.isna(row.get("id")): 
                continue

            meta = self._safe_json_parse(row.get("metadata"))

            if not pd.isna(row.get("mode")):
                meta["mode"] = str(row["mode"]).strip().lower()

            arc_payload = {
                "id": str(row["id"]).strip(),
                "origin": str(row["origin"]).strip(),
                "destination": str(row["destination"]).strip(),
                "capacity": float(row.get("capacity") or 0.0) if not pd.isna(row.get("capacity")) else 0.0,
                "metadata": meta
            }

            if not pd.isna(row.get("speed_avg")):
                try:
                    s_val = float(row["speed_avg"])
                    if s_val > 0:
                        arc_payload["speed_profile"] = {"default": s_val}
                except (ValueError, TypeError):
                    pass

            if not pd.isna(row.get("cost")):
                try:
                    c_val = float(row["cost"])
                    arc_payload["cost_profile"] = {
                        "cost_type": "flat",
                        "params": {"variable_coef": c_val}
                    }
                except (ValueError, TypeError):
                    pass

            clean_arcs.append(arc_payload)

        s, f, _ = ingestor.load_arcs(clean_arcs)
        logger.info(f"✅ Carga Finalizada. Arcos OK: {s} | Rechazados: {f}")

    def _read_from_excel(self):
        """Lógica interna para leer el Excel original."""
        df_nodes = pd.read_excel(
            self.file_path, 
            sheet_name="NODES", 
            dtype={"id": str, "station_type": str}
        )
        df_arcs = pd.read_excel(
            self.file_path, 
            sheet_name="ARCS", 
            dtype={"id": str, "origin": str, "destination": str, "mode": str}
        )
        return df_nodes, df_arcs, "Excel Fast Loader"
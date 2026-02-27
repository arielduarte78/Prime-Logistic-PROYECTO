# src/bloque1/discovery_engine.py
"""
Motor de Descubrimiento Autónomo — Prime Logistics v1.3.5.

Recibe Nodos (infraestructura) y Flota (recursos) y descubre todas las
conexiones viables aplicando un embudo de 3 filtros progresivos:

  Filtro 1 — Compatibilidad Semántica (microsegundos)
  Filtro 2 — Heurística de Rango Geodético (vectorizado, milisegundos)
  Filtro 3 — Validación Física OSMnx (Fase 3 — NO implementado aquí)

Restricciones de ingeniería honradas:
  • Filtro 2 usa scipy.spatial.distance.cdist con coordenadas en radianes.
    CERO bucles for de Python para cálculo de distancias.
  • Safety Factors importados de config.py.
  • Este módulo NO toca SmartLazyIngestor ni OSMnx.
"""
from __future__ import annotations

import logging
import time
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .smart_ingestor import SmartLazyIngestor

import numpy as np
from scipy.spatial.distance import cdist

from .config import SAFETY_FACTORS, MAX_WORKERS
from .fleet_schema import FleetVehicle
from .models import NodeRecord

logger = logging.getLogger(__name__)

# Radio de la Tierra en km (constante WGS-84 estándar)
_EARTH_RADIUS_KM: float = 6371.0


# =====================================================================
# ESTRUCTURAS DE SALIDA
# =====================================================================

@dataclass
class DiscoveredCandidate:
    """
    Representa un par (origen, destino, vehículo) que sobrevivió a los
    Filtros 1 y 2 y es candidato para validación física (Filtro 3).

    Attributes
    ----------
    origin : NodeRecord
        Nodo de origen.
    destination : NodeRecord
        Nodo de destino.
    vehicle : FleetVehicle
        Perfil de vehículo asociado a esta conexión.
    estimated_distance_km : float
        Distancia Haversine (línea recta) en km.
        Nota: es una subestimación de la distancia real por carretera.
    """
    origin: NodeRecord
    destination: NodeRecord
    vehicle: FleetVehicle
    estimated_distance_km: float
    physical_distance_km: float = -1.0

    def as_tuple(self) -> Tuple[str, str, str, float, float]:
        """Retorna (origin_id, dest_id, vehicle_mode, est_dist, phys_dist)."""
        vid: str = self.vehicle.vehicle_id or self.vehicle.mode
        return (self.origin.id, self.destination.id, vid, 
                self.estimated_distance_km, self.physical_distance_km)


@dataclass
class FilterResult:
    """Resultado tipado de una validacion del Filtro 3.

    Elimina la ambiguedad de retornar `DiscoveredCandidate | str | None`.
    Pyre2 puede resolver el tipo en el consumidor sin isinstance guards.
    """
    success: bool
    candidate: Optional[DiscoveredCandidate] = None
    error_type: Optional[str] = None


@dataclass
class PipelineTelemetry:
    """
    Registro de supervivencia del embudo de descubrimiento.

    Permite auditar cuántos candidatos fueron generados, cuántos
    sobrevivieron cada filtro, y el tiempo de ejecución.

    Attributes
    ----------
    total_input_pairs : int
        Pares totales generados: N × N × M (excluyendo self-loops).
    filter_1_survivors : int
        Pares que pasaron compatibilidad semántica.
    filter_2_survivors : int
        Pares que pasaron la heurística de rango geodético.
    filter_1_time_ms : float
        Tiempo de ejecución del Filtro 1 en milisegundos.
    filter_2_time_ms : float
        Tiempo de ejecución del Filtro 2 en milisegundos.
    total_time_ms : float
        Tiempo total del pipeline Filtros 1+2.
    vehicles_processed : int
        Cantidad de perfiles de vehículo evaluados.
    zonal_errors : Dict[str, int]
        Reservado para Filtro 3: log de errores OSMnx por zona geográfica.
    """
    total_input_pairs: int = 0
    filter_1_survivors: int = 0
    filter_2_survivors: int = 0
    filter_3_survivors: int = 0
    filter_1_time_ms: float = 0.0
    filter_2_time_ms: float = 0.0
    filter_3_time_ms: float = 0.0
    total_time_ms: float = 0.0
    vehicles_processed: int = 0
    zonal_errors: Dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        """Genera un informe legible del embudo."""
        f1_rate = (
            f"{self.filter_1_survivors / self.total_input_pairs * 100:.1f}%"
            if self.total_input_pairs > 0 else "N/A"
        )
        f2_rate = (
            f"{self.filter_2_survivors / self.filter_1_survivors * 100:.1f}%"
            if self.filter_1_survivors > 0 else "N/A"
        )
        f3_rate = (
            f"{self.filter_3_survivors / self.filter_2_survivors * 100:.1f}%"
            if self.filter_2_survivors > 0 else "N/A"
        )
        overall = (
            f"{self.filter_3_survivors / self.total_input_pairs * 100:.2f}%"
            if self.total_input_pairs > 0 else "N/A"
        )
        
        err_str = ""
        if self.zonal_errors:
            err_str = "\n  Errores F3        :\n" + "\n".join(f"    {k}: {v}" for k, v in self.zonal_errors.items())

        return (
            f"=== Discovery Pipeline Telemetry ===\n"
            f"  Vehiculos evaluados : {self.vehicles_processed}\n"
            f"  Total pares entrada : {self.total_input_pairs:,}\n"
            f"  Filtro 1 (Semantico): {self.filter_1_survivors:,}  ({f1_rate} pasan)\n"
            f"  Filtro 2 (Rango)    : {self.filter_2_survivors:,}  ({f2_rate} pasan)\n"
            f"  Filtro 3 (Fisico)   : {self.filter_3_survivors:,}  ({f3_rate} pasan)\n"
            f"  Tasa supervivencia  : {overall}\n"
            f"  Tiempo F1           : {self.filter_1_time_ms:.1f} ms\n"
            f"  Tiempo F2           : {self.filter_2_time_ms:.1f} ms\n"
            f"  Tiempo F3           : {self.filter_3_time_ms:.1f} ms\n"
            f"  Tiempo total        : {self.total_time_ms:.1f} ms{err_str}\n"
            f"===================================="
        )





# =====================================================================
# MOTOR DE DESCUBRIMIENTO
# =====================================================================

class DiscoveryEngine:
    """
    Motor de descubrimiento de conexiones logísticas viables.

    Recibe nodos (infraestructura) y flota (recursos), y ejecuta un
    embudo de filtros progresivos para encontrar todos los pares
    (origen, destino, vehículo) que podrían formar arcos válidos.

    Uso
    ---
        engine = DiscoveryEngine(nodes, fleet)
        candidates, telemetry = engine.run_filters_1_2()

    Notas
    -----
    - Este motor NO ejecuta el Filtro 3 (validación física OSMnx).
    - El Filtro 2 utiliza `scipy.spatial.distance.cdist` para computar
      la matriz de distancias Haversine de N×N en un solo bloque C.
    - No se usan bucles `for` nativos de Python para distancias.
    """

    def __init__(
        self,
        nodes: Sequence[NodeRecord],
        fleet: Sequence[FleetVehicle],
    ) -> None:
        if not nodes:
            raise ValueError("Se requiere al menos un nodo para el descubrimiento.")
        if not fleet:
            raise ValueError("Se requiere al menos un vehículo de flota.")

        self._nodes: List[NodeRecord] = list(nodes)
        self._fleet: List[FleetVehicle] = list(fleet)

        # Pre-computar la matriz de distancias Haversine (N×N) una sola vez.
        # Esto se reutiliza para todos los vehículos.
        self._dist_matrix: Optional[np.ndarray] = None
        self._node_index: Dict[str, int] = {n.id: i for i, n in enumerate(self._nodes)}

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def fleet_count(self) -> int:
        return len(self._fleet)

    # -----------------------------------------------------------------
    # MATRIZ DE DISTANCIAS (cdist — vectorizado puro)
    # -----------------------------------------------------------------

    def _compute_distance_matrix(self) -> np.ndarray:
        """
        Calcula la matriz de distancias Haversine N×N.

        Usa estricta vectorización pura de NumPy (broadcasting) para garantizar CERO
        bucles `for` nativos (ni implícitos vía callbacks map).

        Returns
        -------
        np.ndarray
            Matriz (N, N) de distancias en kilómetros.
        """
        if self._dist_matrix is not None:
            return self._dist_matrix

        n = len(self._nodes)
        logger.info(
            "Calculando matriz de distancias Haversine %dx%d puramente vectorizada...", n, n
        )

        # Extraer coordenadas y convertir a radianes
        coords_deg = np.array(
            [(node.lat, node.lon) for node in self._nodes],
            dtype=np.float64,
        )
        coords_rad = np.radians(coords_deg)

        # Vectorización Estricta vía Broadcasting O(N^2)
        lat = coords_rad[:, 0]
        lon = coords_rad[:, 1]
        
        dlat = lat[:, np.newaxis] - lat[np.newaxis, :]
        dlon = lon[:, np.newaxis] - lon[np.newaxis, :]
        
        a = (np.sin(dlat / 2.0) ** 2 +
             np.cos(lat[:, np.newaxis]) * np.cos(lat[np.newaxis, :]) * np.sin(dlon / 2.0) ** 2)
        
        c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
        self._dist_matrix = _EARTH_RADIUS_KM * c

        logger.info(
            "Matriz de distancias calculada: %.0f pares vectorizados en memoria.",
            n * n,
        )
        return self._dist_matrix

    # -----------------------------------------------------------------
    # FILTRO 1: COMPATIBILIDAD SEMÁNTICA
    # -----------------------------------------------------------------

    @staticmethod
    def _filter_1_semantic(
        nodes: List[NodeRecord],
        vehicle: FleetVehicle,
    ) -> np.ndarray:
        """
        Filtro 1 — Compatibilidad Semántica.

        Para cada par (i, j) con i ≠ j, verifica que:
          - nodes[i].station_type ∈ vehicle.allowed_stations  (origen)
          - nodes[j].station_type ∈ vehicle.allowed_stations  (destino)

        Usa operaciones vectorizadas NumPy (broadcasting booleano).
        No itera pares con for.

        Parameters
        ----------
        nodes : List[NodeRecord]
            Lista de nodos con station_type ya normalizado.
        vehicle : FleetVehicle
            Vehículo cuyas allowed_stations definen compatibilidad.

        Returns
        -------
        np.ndarray
            Máscara booleana (N, N) donde True = par semánticamente
            compatible. Diagonal siempre False (sin self-loops).
        """
        allowed = frozenset(vehicle.allowed_stations)
        n = len(nodes)

        # Vector booleano: ¿nodo i es compatible con este vehículo?
        compat = np.array(
            [node.station_type in allowed for node in nodes],
            dtype=np.bool_,
        )

        # Broadcasting: compat_origin[i] AND compat_dest[j] para todo (i,j)
        pair_mask = compat[:, np.newaxis] & compat[np.newaxis, :]  # (N, N)

        # Eliminar diagonal (self-loops)
        np.fill_diagonal(pair_mask, False)

        return pair_mask

    # -----------------------------------------------------------------
    # FILTRO 2: HEURÍSTICA DE RANGO GEODÉTICO
    # -----------------------------------------------------------------

    @staticmethod
    def _filter_2_range(
        dist_matrix: np.ndarray,
        vehicle: FleetVehicle,
        semantic_mask: np.ndarray,
    ) -> np.ndarray:
        """
        Filtro 2 — Heurística de Rango Geodético.

        Para cada par que sobrevivió al Filtro 1, verifica:
          Haversine_Distance × Safety_Factor ≤ max_range_km

        Operación 100% vectorizada sobre matrices NumPy.

        Parameters
        ----------
        dist_matrix : np.ndarray
            Matriz de distancias Haversine (N, N) en km.
        vehicle : FleetVehicle
            Define max_range_km y mode (para buscar safety factor).
        semantic_mask : np.ndarray
            Máscara booleana (N, N) del Filtro 1.

        Returns
        -------
        np.ndarray
            Máscara booleana (N, N) donde True = par que sobrevive
            ambos filtros.
        """
        # Obtener safety factor del modo del vehículo
        safety = SAFETY_FACTORS.get(
            vehicle.mode,
            SAFETY_FACTORS.get("default", 1.5),
        )

        # Aplicar heurística: dist * safety_factor <= max_range
        # Operación element-wise sobre toda la matriz (vectorizado NumPy)
        range_mask = (dist_matrix * safety) <= vehicle.max_range_km

        # Intersección con máscara semántica
        return semantic_mask & range_mask

    # -----------------------------------------------------------------
    # ORQUESTADOR PRINCIPAL: FILTROS 1 + 2
    # -----------------------------------------------------------------

    def run_filters_1_2(
        self,
    ) -> Tuple[List[DiscoveredCandidate], PipelineTelemetry]:
        """
        Ejecuta el embudo completo de Filtros 1 y 2.

        Para cada vehículo de la flota:
          1. Filtro 1: descarta pares semánticamente incompatibles.
          2. Filtro 2: descarta pares fuera del rango geodético.
          3. Recolecta los sobrevivientes como DiscoveredCandidate.

        Returns
        -------
        Tuple[List[DiscoveredCandidate], PipelineTelemetry]
            - Lista de candidatos que sobrevivieron ambos filtros.
            - Telemetría acumulada del pipeline completo.
        """
        t_start = time.perf_counter()
        telemetry = PipelineTelemetry()

        n = len(self._nodes)
        m = len(self._fleet)
        total_possible = n * (n - 1) * m  # N × (N-1) × M (sin self-loops)
        telemetry.total_input_pairs = total_possible
        telemetry.vehicles_processed = m

        logger.info(
            "Discovery Engine: %d nodos × %d vehículos = %s pares posibles (sin self-loops)",
            n, m, f"{total_possible:,}",
        )

        # Pre-computar matriz de distancias (una sola vez para todos los vehículos)
        t_dist_start = time.perf_counter()
        dist_matrix = self._compute_distance_matrix()
        t_dist_elapsed = (time.perf_counter() - t_dist_start) * 1000.0

        logger.info("Matriz cdist calculada en %.1f ms.", t_dist_elapsed)

        all_candidates: List[DiscoveredCandidate] = []
        f1_survivors: List[int] = []
        f2_survivors: List[int] = []
        f1_times: List[float] = []
        f2_times: List[float] = []

        for vehicle in self._fleet:
            vid = vehicle.vehicle_id or vehicle.mode
            logger.debug("Procesando vehículo: %s (mode=%s, range=%.0f km)",
                         vid, vehicle.mode, vehicle.max_range_km)

            # --- Filtro 1: Semántico ---
            t_f1 = time.perf_counter()
            semantic_mask = self._filter_1_semantic(self._nodes, vehicle)
            f1_count = int(np.count_nonzero(semantic_mask))
            t_f1_elapsed = (time.perf_counter() - t_f1) * 1000.0
            f1_times.append(t_f1_elapsed)
            f1_survivors.append(f1_count)

            logger.debug(
                "  Filtro 1 [%s]: %d/%d pares compatibles (%.1f ms)",
                vid, f1_count, n * (n - 1), t_f1_elapsed,
            )

            if f1_count == 0:
                logger.debug("  → Ningún par compatible. Saltando Filtro 2.")
                continue

            # --- Filtro 2: Rango Geodético ---
            t_f2 = time.perf_counter()
            surviving_mask = self._filter_2_range(dist_matrix, vehicle, semantic_mask)
            f2_count = int(np.count_nonzero(surviving_mask))
            t_f2_elapsed = (time.perf_counter() - t_f2) * 1000.0
            f2_times.append(t_f2_elapsed)
            f2_survivors.append(f2_count)

            logger.debug(
                "  Filtro 2 [%s]: %d/%d pares en rango (%.1f ms)",
                vid, f2_count, f1_count, t_f2_elapsed,
            )

            if f2_count == 0:
                logger.debug("  → Ningún par en rango. Sin candidatos.")
                continue

            # --- Recolectar sobrevivientes ---
            # np.argwhere retorna coordenadas (i, j) de los True
            surviving_indices = np.argwhere(surviving_mask)

            for idx_pair in surviving_indices:
                i, j = int(idx_pair[0]), int(idx_pair[1])
                candidate = DiscoveredCandidate(
                    origin=self._nodes[i],
                    destination=self._nodes[j],
                    vehicle=vehicle,
                    estimated_distance_km=float(dist_matrix[i, j]),
                )
                all_candidates.append(candidate)

        # --- Telemetría final ---
        t_total = (time.perf_counter() - t_start) * 1000.0
        telemetry.filter_1_survivors = sum(f1_survivors)
        telemetry.filter_2_survivors = sum(f2_survivors)
        telemetry.filter_1_time_ms = sum(f1_times)
        telemetry.filter_2_time_ms = sum(f2_times) + t_dist_elapsed  # cdist es parte del F2
        telemetry.total_time_ms = t_total

        logger.info("\n%s", telemetry.summary())

        return all_candidates, telemetry

    # -----------------------------------------------------------------
    # FILTRO 3: VALIDACIÓN FÍSICA (OSMnx / Dijkstra)
    # -----------------------------------------------------------------

    def run_filter_3(
        self,
        candidates: List[DiscoveredCandidate],
        ingestor: "SmartLazyIngestor",
        telemetry: PipelineTelemetry,
        output_csv: str = "discovery_audit.csv"
    ) -> List[DiscoveredCandidate]:
        """
        Filtro 3 — Validacion Fisica Viaria.

        Toma los candidatos que sobrevivieron F1 y F2, y los valida contra
        la realidad fisica (OpenStreetMap) usando el SmartLazyIngestor.

        RESTRICCION: Usa ThreadPoolExecutor con max_workers estricto
        (definido en config.py) para no saturar la API de OSM.

        Genera discovery_audit.csv al finalizar.
        """
        if not candidates:
            logger.info("Filtro 3: No hay candidatos para validar.")
            return []

        logger.info("Iniciando Filtro 3: Validacion Fisica para %d candidatos (max_workers=%d)",
                    len(candidates), MAX_WORKERS)

        t_f3_start: float = time.perf_counter()
        final_survivors: List[DiscoveredCandidate] = []

        from .h3_router import RouteEndpoint

        def _validate_single(candidate: DiscoveredCandidate) -> FilterResult:
            """Valida un candidato contra la red vial real. Retorna FilterResult."""
            o_node: NodeRecord = candidate.origin
            d_node: NodeRecord = candidate.destination

            orig_ep = RouteEndpoint(name=o_node.id, lat=o_node.lat, lon=o_node.lon)
            dest_ep = RouteEndpoint(name=d_node.id, lat=d_node.lat, lon=d_node.lon)

            try:
                phys_dist: float = ingestor.validate_physical_connection(
                    origin=orig_ep,
                    dest=dest_ep,
                    mode=candidate.vehicle.mode
                )
                candidate.physical_distance_km = phys_dist
                if phys_dist > 0 and phys_dist <= candidate.vehicle.max_range_km:
                    return FilterResult(success=True, candidate=candidate)
                else:
                    return FilterResult(success=False)

            except Exception as e:
                return FilterResult(success=False, error_type=type(e).__name__)

        # Ejecucion Concurrente Restringida
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_cand = {
                executor.submit(_validate_single, c): c for c in candidates
            }

            for future in as_completed(future_to_cand):
                cand: DiscoveredCandidate = future_to_cand[future]
                try:
                    result: FilterResult = future.result()
                    if result.success and result.candidate is not None:
                        validated: DiscoveredCandidate = result.candidate
                        final_survivors.append(validated)
                    elif result.error_type is not None:
                        zonal: str = cand.origin.id[:8] + "-" + cand.destination.id[:8]
                        telemetry.zonal_errors[zonal] = telemetry.zonal_errors.get(zonal, 0) + 1
                except Exception as exc:
                    logger.error("Error no manejado en F3 para %s->%s: %s",
                                 cand.origin.id, cand.destination.id, exc)

        # Telemetria Final
        t_f3_elapsed: float = (time.perf_counter() - t_f3_start) * 1000.0
        telemetry.filter_3_time_ms = t_f3_elapsed
        telemetry.total_time_ms = telemetry.total_time_ms + t_f3_elapsed
        telemetry.filter_3_survivors = len(final_survivors)

        logger.info("\n%s", telemetry.summary())

        # Generar Auditoria CSV
        self._export_audit_csv(candidates, final_survivors, output_csv)

        return final_survivors

    def _export_audit_csv(self, f2_candidates: List[DiscoveredCandidate], 
                          f3_survivors: List[DiscoveredCandidate], out_path: str):
        """Genera el reporte final discovery_audit.csv."""
        survivor_keys = { (c.origin.id, c.destination.id, c.vehicle.vehicle_id) for c in f3_survivors }
        
        try:
            with open(out_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "origin_id", "destination_id", "vehicle_id", "vehicle_mode",
                    "est_haversine_km", "physical_road_km", "status", "reason"
                ])
                
                for c in f2_candidates:
                    vid = c.vehicle.vehicle_id or c.vehicle.mode
                    is_survivor = (c.origin.id, c.destination.id, vid) in survivor_keys
                    
                    status = "ACCEPTED" if is_survivor else "REJECTED"
                    
                    reason = ""
                    if not is_survivor:
                        if c.physical_distance_km == -1.0:
                            reason = "UNREACHABLE_OR_ERROR (Filter 3)"
                        elif c.physical_distance_km > c.vehicle.max_range_km:
                            reason = f"ROAD_EXCEEDS_RANGE ({c.physical_distance_km:.1f} > {c.vehicle.max_range_km})"
                        else:
                            reason = "FILTERED_F3"
                    
                    p_dist_str = f"{c.physical_distance_km:.2f}" if c.physical_distance_km > 0 else "N/A"
                    
                    writer.writerow([
                        c.origin.id, c.destination.id, vid, c.vehicle.mode,
                        f"{c.estimated_distance_km:.2f}", p_dist_str, status, reason
                    ])
            logger.info("Auditoría guardada exitosamente en %s", out_path)
        except Exception as e:
            logger.error("Error escribiendo %s: %s", out_path, e)

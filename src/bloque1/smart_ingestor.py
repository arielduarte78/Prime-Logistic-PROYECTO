"""Orquestador Principal de Ingesta (Smart Lazy Loading) para Prime Logistics v1.2."""
from __future__ import annotations

import logging
import time
from typing import Optional

import networkx as nx
import osmnx as ox
from shapely.geometry import Polygon
from shapely.ops import unary_union
from filelock import FileLock, Timeout

# Importamos las piezas que ya construimos
from src.bloque1.config import H3RouterConfig
from src.bloque1.h3_router import RouteEndpoint, build_h3_corridor, split_cells
from src.bloque1.cache_manager import SafeCacheManager

logger = logging.getLogger(__name__)


class SmartLazyIngestor:
    # Modos de transporte soportados
    VALID_MODES = {"truck", "car", "bus"}

    def __init__(self, config: H3RouterConfig, cache_manager: SafeCacheManager):
        self.config = config
        self.cache = cache_manager

        # Ajustes de OSMnx (Importación explícita para evitar errores de versión)
        try:
            from osmnx import settings as ox_settings
            ox_settings.timeout = 180
            ox_settings.use_cache = False
        except Exception as e:
            logger.warning("No se pudo configurar OSMnx: %s", e)

        # Directorio para locks de descarga (dentro del caché)
        self.download_lock_dir = cache_manager.lock_dir / "downloads"
        self.download_lock_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------------
    # Métricas (hook a cache manager, que a su vez tiene _emit_metric)
    # ----------------------------------------------------------------------

    def _emit_metric(self, name: str, value: float = 1.0, labels: dict | None = None):
        """Delega en el cache manager (que tiene el hook a producción)."""
        self.cache._emit_metric(name, value, labels)

    # ----------------------------------------------------------------------
    # Adaptador para graph_from_polygon (compatible OSMnx v1 y v2)
    # ----------------------------------------------------------------------
    def _graph_from_polygon_adapter(self, polygon, **kwargs):
        """
        Intenta usar la API moderna (osmnx >= 2.0) y fallback a la clásica (1.x).
        """
        try:
            # Intentar con la nueva ubicación (osmnx.graph.graph_from_polygon)
            from osmnx import graph
            return graph.graph_from_polygon(polygon, **kwargs)
        except (ImportError, AttributeError):
            # Fallback a la función original (osmnx 1.x)
            return ox.graph_from_polygon(polygon, **kwargs)

    # ----------------------------------------------------------------------
    # Conversión de celdas a polígono (con manejo seguro de errores)
    # ----------------------------------------------------------------------

    def _cells_to_polygon(self, cells: tuple[str, ...], segment_name: str = "") -> Optional[Polygon]:
        """Convierte una lista de hexágonos H3 en un polígono gigante para descargar."""
        if not cells:
            return None

        # FIX: Adaptador universal para los límites del hexágono (boundary)
        import h3
        boundary_func = getattr(h3, "cell_to_boundary", None) or getattr(h3, "h3_to_geo_boundary", None)
        
        if not boundary_func:
            logger.error("No se encontró la función de boundary en la librería H3 instalada.")
            return None

        polys = []
        for cell in cells:
            try:
                boundary = boundary_func(cell)  # Devuelve [(lat, lon), ...]
                # OSMnx usa (lon, lat)
                lon_lat = [(lon, lat) for lat, lon in boundary]
                polys.append(Polygon(lon_lat))
            except Exception as e:
                logger.warning("Celda H3 inválida o error al obtener límites: %s, error: %s", cell, e)
                self._emit_metric("osm.cell_to_boundary.error", labels={"cell": str(cell)[:8]})

        if not polys:
            if segment_name:
                self._emit_metric("osm.polygon.empty", labels={
                    "segment": segment_name,
                    "cells": str(len(cells))
                })
                logger.warning("Polígono vacío para segmento %s (%d celdas).", segment_name, len(cells))
            return None

        # Pegamos todos los hexágonos para hacer una sola llamada a internet
        return unary_union(polys)

    # ----------------------------------------------------------------------
    # Validación de parámetros
    # ----------------------------------------------------------------------

    def _validate_mode(self, mode: str) -> None:
        if mode not in self.VALID_MODES:
            raise ValueError(f"Modo inválido: {mode}. Debe ser uno de {self.VALID_MODES}")

    # ----------------------------------------------------------------------
    # Flujo principal
    # ----------------------------------------------------------------------

    def get_or_build_graph(
        self,
        origin: RouteEndpoint,
        dest: RouteEndpoint,
        mode: str = "truck"
    ) -> nx.MultiDiGraph:
        """El Flujo Principal: Caché -> Matemáticas -> Descarga -> Fusión -> Guardado."""
        self._validate_mode(mode)
        start_total = time.perf_counter()

        logger.info("🗺️ Solicitando ruta: %s -> %s (modo: %s)", origin.name, dest.name, mode)

        # 1. Intentar cargar desde caché
        cached_graph = self.cache.load_graph(
            origin=origin.name,
            dest=dest.name,
            zoom=self.config.resolution,
            profile=self.config.buffer_rings,
            mode=mode
        )
        if cached_graph is not None:
            logger.info("✅ Caché HIT: mapa recuperado.")
            self._emit_metric("cache.hit", labels={"mode": mode})
            # Registrar tiempo total aunque sea caché
            elapsed_total = (time.perf_counter() - start_total) * 1000
            self._emit_metric("ingestor.total.duration_ms", elapsed_total,
                              labels={"cache": "hit", "mode": mode})
            return cached_graph

        logger.info("🌐 Caché MISS. Iniciando descarga (Smart Lazy Loading)...")
        self._emit_metric("cache.miss", labels={"mode": mode})

        # 2. Lock de descarga para evitar duplicados concurrentes
        key = self.cache._generate_key(origin.name, dest.name, self.config.resolution,
                                       self.config.buffer_rings, mode)
        lock_path = self.download_lock_dir / f"{key}.lock"
        download_lock = FileLock(str(lock_path), timeout=60)  # 1 minuto de espera máxima

        try:
            with download_lock:
                # Volver a comprobar caché por si otro proceso ya lo guardó mientras esperábamos el lock
                cached_graph = self.cache.load_graph(
                    origin=origin.name,
                    dest=dest.name,
                    zoom=self.config.resolution,
                    profile=self.config.buffer_rings,
                    mode=mode
                )
                if cached_graph is not None:
                    logger.info("✅ Caché HIT (después de adquirir lock): mapa recuperado.")
                    self._emit_metric("cache.hit", labels={"mode": mode})
                    elapsed_total = (time.perf_counter() - start_total) * 1000
                    self._emit_metric("ingestor.total.duration_ms", elapsed_total,
                                      labels={"cache": "hit", "mode": mode})
                    return cached_graph

                # 3. Matemáticas: Calcular Corredor
                start_math = time.perf_counter()
                corredor = build_h3_corridor(
                    origin, dest,
                    resolution=self.config.resolution,
                    buffer_rings=self.config.buffer_rings,
                    max_cells=self.config.max_cells
                )
                self._emit_metric("h3.corridor.duration_ms",
                                  value=(time.perf_counter() - start_math) * 1000)

                # Guardamos número de celdas para métricas de error
                total_cells = len(corredor.buffered_cells)

                # Dividir en zonas
                loc_o, loc_d, trunk = split_cells(
                    corredor.buffered_cells,
                    corredor.origin_cell,
                    corredor.destination_cell,
                    local_rings=self.config.local_rings
                )

                # 4. Geometría: Crear los 3 Polígonos (con métrica de vacío y cantidad de celdas)
                poly_origen = self._cells_to_polygon(loc_o, segment_name="origen")
                poly_destino = self._cells_to_polygon(loc_d, segment_name="destino")
                poly_troncal = self._cells_to_polygon(trunk, segment_name="troncal")

                # 5. Descargas OSMnx (usando adaptador compatible)
                subgraphs = []
                # Filtro para autopistas (solo troncales principales)
                trunk_filter = '["highway"~"motorway|motorway_link|trunk|trunk_link"]'

                try:
                    if poly_origen and not poly_origen.is_empty:
                        logger.info("   📥 Bajando mapa local Origen (%s hexágonos)...", len(loc_o))
                        g_origen = self._graph_from_polygon_adapter(
                            poly_origen, network_type="drive", simplify=True
                        )
                        if g_origen.number_of_nodes() > 0 and g_origen.number_of_edges() > 0:
                            # Verificación adicional: al menos una arista tiene atributo highway
                            if any('highway' in data for _, _, data in g_origen.edges(data=True)):
                                subgraphs.append(g_origen)
                                self._emit_metric("osm.download.success", labels={
                                    "segment": "origen", "mode": mode, "cells": str(total_cells)
                                })
                            else:
                                logger.warning("Subgrafo origen sin atributos highway (ruido), se omite.")
                                self._emit_metric("osm.download.empty", labels={
                                    "segment": "origen", "mode": mode, "cells": str(total_cells)
                                })
                        else:
                            logger.warning("Subgrafo origen vacío o sin aristas, se omite.")
                            self._emit_metric("osm.download.empty", labels={
                                "segment": "origen", "mode": mode, "cells": str(total_cells)
                            })

                    if poly_destino and not poly_destino.is_empty:
                        logger.info("   📥 Bajando mapa local Destino (%s hexágonos)...", len(loc_d))
                        g_destino = self._graph_from_polygon_adapter(
                            poly_destino, network_type="drive", simplify=True
                        )
                        if g_destino.number_of_nodes() > 0 and g_destino.number_of_edges() > 0:
                            if any('highway' in data for _, _, data in g_destino.edges(data=True)):
                                subgraphs.append(g_destino)
                                self._emit_metric("osm.download.success", labels={
                                    "segment": "destino", "mode": mode, "cells": str(total_cells)
                                })
                            else:
                                logger.warning("Subgrafo destino sin atributos highway (ruido), se omite.")
                                self._emit_metric("osm.download.empty", labels={
                                    "segment": "destino", "mode": mode, "cells": str(total_cells)
                                })
                        else:
                            logger.warning("Subgrafo destino vacío o sin aristas, se omite.")
                            self._emit_metric("osm.download.empty", labels={
                                "segment": "destino", "mode": mode, "cells": str(total_cells)
                            })

                    if poly_troncal and not poly_troncal.is_empty:
                        logger.info("   📥 Bajando Autopistas Troncales (%s hexágonos)...", len(trunk))
                        try:
                            g_troncal = self._graph_from_polygon_adapter(
                                poly_troncal, custom_filter=trunk_filter, simplify=True
                            )
                            if g_troncal.number_of_nodes() > 0 and g_troncal.number_of_edges() > 0:
                                if any('highway' in data for _, _, data in g_troncal.edges(data=True)):
                                    subgraphs.append(g_troncal)
                                    self._emit_metric("osm.download.success", labels={
                                        "segment": "troncal", "mode": mode, "cells": str(total_cells)
                                    })
                                else:
                                    logger.warning("Subgrafo troncal sin atributos highway (ruido), se omite.")
                                    self._emit_metric("osm.download.empty", labels={
                                        "segment": "troncal", "mode": mode, "cells": str(total_cells)
                                    })
                            else:
                                logger.warning("Subgrafo troncal vacío o sin aristas, se omite.")
                                self._emit_metric("osm.download.empty", labels={
                                    "segment": "troncal", "mode": mode, "cells": str(total_cells)
                                })
                        except ValueError:
                            logger.info("   ℹ️ No se encontraron autopistas troncales en esta zona (Ruta corta/urbana).")

                except Exception as e:
                    logger.exception("💥 Error crítico descargando de OpenStreetMap.")
                    self._emit_metric("osm.download.error", labels={
                        "error": type(e).__name__,
                        "origin": origin.name[:8],
                        "dest": dest.name[:8],
                        "mode": mode,
                        "cells": str(total_cells)
                    })
                    raise RuntimeError("Fallo al descargar mapas. Verifica tu conexión o el tamaño de la ruta.") from e

                if not subgraphs:
                    raise RuntimeError("No se pudo descargar ningún segmento de mapa.")

                # 6. Fusión (Armar el Frankenstein)
                logger.info("   🔗 Fusionando los mapas descargados...")
                start_fusion = time.perf_counter()

                # Verificar posibles solapamientos (solo para diagnóstico)
                all_nodes = set()
                for g in subgraphs:
                    new_nodes = set(g.nodes)
                    overlap = all_nodes & new_nodes
                    if overlap:
                        logger.warning("Se detectaron %d nodos compartidos entre segmentos. Puede haber inconsistencias.",
                                       len(overlap))
                        self._emit_metric("graph.fusion.overlap_nodes", value=len(overlap),
                                          labels={"mode": mode, "segments": str(len(subgraphs)),
                                                  "cells": str(total_cells)})
                    all_nodes.update(new_nodes)

                final_graph = nx.compose_all(subgraphs)
                # Reemplazo de ox.utils_graph.remove_isolated_nodes por NetworkX puro
                final_graph.remove_nodes_from(list(nx.isolates(final_graph)))

                fusion_duration = (time.perf_counter() - start_fusion) * 1000
                self._emit_metric("graph.fusion.duration_ms", fusion_duration,
                                  labels={"mode": mode, "cells": str(total_cells)})

                # Métricas del grafo resultante
                self._emit_metric("graph.nodes_total", value=final_graph.number_of_nodes(),
                                  labels={"mode": mode, "cells": str(total_cells)})
                self._emit_metric("graph.edges_total", value=final_graph.number_of_edges(),
                                  labels={"mode": mode, "cells": str(total_cells)})

                # 7. Guardar en la Caja Fuerte
                logger.info("   🏦 Guardando mapa en Caché Seguro...")
                save_ok = self.cache.save_graph(
                    graph=final_graph,
                    origin=origin.name,
                    dest=dest.name,
                    zoom=self.config.resolution,
                    profile=self.config.buffer_rings,
                    mode=mode
                )
                if not save_ok:
                    logger.error("Fallo al guardar el grafo en caché, pero se devuelve el grafo descargado.")

                # Latencia total
                elapsed_total = (time.perf_counter() - start_total) * 1000
                self._emit_metric("ingestor.total.duration_ms", elapsed_total,
                                  labels={"cache": "miss", "mode": mode,
                                          "segments_downloaded": str(len(subgraphs)),
                                          "cells": str(total_cells)})

                return final_graph

        except Timeout:
            logger.error("Timeout esperando lock de descarga para %s -> %s", origin.name, dest.name)
            self._emit_metric("download.lock.timeout", labels={
                "origin": origin.name[:8],
                "dest": dest.name[:8],
                "mode": mode
            })
            raise RuntimeError("Concurrencia de descargas: timeout al adquirir lock. Intenta más tarde.")

        except Exception as e:
            logger.exception("Error inesperado en get_or_build_graph")
            # Intentar obtener total_cells si está definido
            cells_label = str(total_cells) if 'total_cells' in locals() else "unknown"
            self._emit_metric("ingestor.error", labels={
                "error": type(e).__name__,
                "origin": origin.name[:8],
                "dest": dest.name[:8],
                "mode": mode,
                "cells": cells_label
            })
            raise
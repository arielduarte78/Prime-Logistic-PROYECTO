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
from .config import H3RouterConfig
from .h3_router import RouteEndpoint, build_h3_corridor, split_cells
from .cache_manager import SafeCacheManager

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
            ox_settings.timeout = 180  # type: ignore[attr-defined]
            ox_settings.use_cache = True
            ox_settings.cache_folder = "./data/osmnx_http_cache"
        except Exception as e:
            logger.warning("No se pudo configurar OSMnx: %s", e)

        # Directorio para locks de descarga (dentro del caché)
        self.download_lock_dir = cache_manager.lock_dir / "downloads"
        self.download_lock_dir.mkdir(parents=True, exist_ok=True)

        # Caché en memoria para cálculos de Dijkstra (Filter 3)
        # Clave: (origin_id, dest_id, mode, resolution, buffer_rings)
        # Valor: distancia en km (float) o -1.0 si es inalcanzable
        self._dijkstra_cache: dict[tuple, float] = {}

    # ----------------------------------------------------------------------
    # Métricas (hook a cache manager, que a su vez tiene _emit_metric)
    # ----------------------------------------------------------------------

    def _emit_metric(self, name: str, value: float = 1.0, labels: dict | None = None):
        """Delega en el cache manager (que tiene el hook a producción)."""
        self.cache._emit_metric(name, value, labels)

    # ----------------------------------------------------------------------
    # Adaptador para graph_from_polygon (compatible OSMnx v1 y v2) con BACKOFF
    # ----------------------------------------------------------------------
    def _graph_from_polygon_adapter(self, polygon, **kwargs):
        """
        Intenta usar la API moderna (osmnx >= 2.0) y fallback a la clásica (1.x).
        Implementa Strict Exponential Backoff para protección contra HTTP 429.
        """
        max_retries = 5
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                # Intentar con la nueva ubicación (osmnx.graph.graph_from_polygon)
                from osmnx import graph
                return graph.graph_from_polygon(polygon, **kwargs)
            except (ImportError, AttributeError):
                # Fallback a la función original (osmnx 1.x)
                try:
                    return ox.graph_from_polygon(polygon, **kwargs)
                except Exception as e:
                    if attempt < max_retries - 1:
                        sleep_time = base_delay * (2 ** attempt)
                        logger.warning("OSMnx error (intento %d/%d): %s. Backoff %.1fs...", 
                                       attempt + 1, max_retries, str(e)[:100], sleep_time)
                        time.sleep(sleep_time)
                        continue
                    raise
            except Exception as e:
                # Otros errores de red/API (ej. HTTP 429 Too Many Requests)
                if attempt < max_retries - 1:
                    sleep_time = base_delay * (2 ** attempt)
                    logger.warning("OSMnx API error (intento %d/%d): %s. Backoff %.1fs...", 
                                   attempt + 1, max_retries, str(e)[:100], sleep_time)
                    time.sleep(sleep_time)
                    continue
                logger.error("Fallo definitivo de OSMnx tras %d intentos.", max_retries)
                raise

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
        result = unary_union(polys)
        if isinstance(result, Polygon):
            return result
        return None  # Non-polygon geometry (e.g., MultiPolygon or Point)

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
        """El Flujo Principal: Matemáticas -> Descarga OSMnx (con HTTP cache) -> Fusión -> Retorno."""
        self._validate_mode(mode)
        start_total = time.perf_counter()

        logger.info("🗺️ Solicitando ruta: %s -> %s (modo: %s)", origin.name, dest.name, mode)

        try:
            # 1. Matemáticas: Calcular Corredor
            start_math = time.perf_counter()
            total_cells = 0  # Initialize before use
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

            # 2. Geometría: Crear los 3 Polígonos (con métrica de vacío y cantidad de celdas)
            poly_origen = self._cells_to_polygon(loc_o, segment_name="origen")
            poly_destino = self._cells_to_polygon(loc_d, segment_name="destino")
            poly_troncal = self._cells_to_polygon(trunk, segment_name="troncal")

            # 3. Descargas OSMnx (usando adaptador compatible, interceptará HTTP cache automáticamente)
            subgraphs = []
            # Filtro para autopistas (solo troncales principales)
            trunk_filter = '["highway"~"motorway|motorway_link|trunk|trunk_link"]'

            try:
                if poly_origen and not poly_origen.is_empty:
                    logger.info("   📥 Bajando mapa local Origen (%s hexágonos)...", len(loc_o))
                    g_origen = self._graph_from_polygon_adapter(
                        poly_origen, network_type="drive", simplify=True
                    )
                    if g_origen is not None and g_origen.number_of_nodes() > 0 and g_origen.number_of_edges() > 0:
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
                    if g_destino is not None and g_destino.number_of_nodes() > 0 and g_destino.number_of_edges() > 0:
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
                        if g_troncal is not None and g_troncal.number_of_nodes() > 0 and g_troncal.number_of_edges() > 0:
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

            # 4. Fusión (Armar el Frankenstein)
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


            # Latencia total
            elapsed_total = (time.perf_counter() - start_total) * 1000
            self._emit_metric("ingestor.total.duration_ms", elapsed_total,
                              labels={"cache": "miss", "mode": mode,
                                      "segments_downloaded": str(len(subgraphs)),
                                      "cells": str(total_cells)})

            return final_graph

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

    # ----------------------------------------------------------------------
    # V1.3.5: Validación Física (Filter 3)
    # ----------------------------------------------------------------------

    def validate_physical_connection(
        self,
        origin: RouteEndpoint,
        dest: RouteEndpoint,
        mode: str = "truck"
    ) -> float:
        """
        Filter 3: Valida físicamente la conexión descargando/recuperando la red OSM
        y calculando la distancia real por carretera mediante Dijkstra.

        Utiliza un caché en memoria (_dijkstra_cache) para evitar recálculos
        redundantes del mismo par bajo las mismas condiciones.

        Parameters
        ----------
        origin : RouteEndpoint
            Punto de origen.
        dest : RouteEndpoint
            Punto de destino.
        mode : str
            Modo de transporte (afecta la topología descargada).

        Returns
        -------
        float
            Distancia tramo por calle en kilómetros.
            Retorna -1.0 si los nodos no están conectados o en caso de error de red.
        """
        # 1. Check in-memory Dijkstra cache
        cache_key = (origin.name, dest.name, mode, self.config.resolution, self.config.buffer_rings)
        if cache_key in self._dijkstra_cache:
            return self._dijkstra_cache[cache_key]

        try:
            # 2. Obtener el grafo (Caché disco o OSMnx download con backoff)
            G = self.get_or_build_graph(origin, dest, mode)

            if G.number_of_nodes() == 0:
                logger.warning("Grafo vacío para %s -> %s", origin.name, dest.name)
                self._dijkstra_cache[cache_key] = -1.0
                return -1.0

            # 3. Mapeo Dinámico de Nodos (Resolución Topológica Estricta)
            # Obligatorio para evitar errores de ID cuando OSMnx simplifica grafos o carga desde el caché
            orig_node = ox.distance.nearest_nodes(G, origin.lon, origin.lat)
            dest_node = ox.distance.nearest_nodes(G, dest.lon, dest.lat)

            # 4. Calcular el camino más corto (Dijkstra) usando la longitud física de la calle
            distance_meters = nx.shortest_path_length(G, orig_node, dest_node, weight='length')
            
            distance_km = distance_meters / 1000.0
            
            # Guardamos en caché en memoria y retornamos
            self._dijkstra_cache[cache_key] = distance_km
            logger.info("Filter 3 completado: %s -> %s = %.2f km (por calle)", 
                        origin.name, dest.name, distance_km)
            return distance_km

        except nx.NetworkXNoPath:
            logger.warning("Degradación (No Path): No hay camino físico posible entre %s y %s en el grafo descargado.", 
                           origin.name, dest.name)
            self._dijkstra_cache[cache_key] = -1.0
            return -1.0
        except nx.NodeNotFound as e:
            logger.warning("Degradación (NodeNotFound): Falla resolviendo proyección topológica cerca de %s/%s. Detalle: %s", 
                           origin.name, dest.name, str(e))
            self._dijkstra_cache[cache_key] = -1.0
            return -1.0
        except Exception as e:
            logger.error("Error inesperado en Filter 3 (%s -> %s): %s", origin.name, dest.name, str(e))
            self._dijkstra_cache[cache_key] = -1.0
            return -1.0
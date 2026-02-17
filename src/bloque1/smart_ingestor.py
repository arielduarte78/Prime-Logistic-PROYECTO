"""Orquestador Principal de Ingesta (Smart Lazy Loading) para Prime Logistics v1.2."""
from __future__ import annotations

import logging
from typing import List

import networkx as nx
import osmnx as ox
from shapely.geometry import Polygon
from shapely.ops import unary_union
import h3

from src.bloque1.config import H3RouterConfig
from src.bloque1.h3_router import RouteEndpoint, build_h3_corridor, split_cells
from src.bloque1.cache_manager import SafeCacheManager

logger = logging.getLogger(__name__)

class SmartLazyIngestor:
    def __init__(self, config: H3RouterConfig, cache_manager: SafeCacheManager):
        self.config = config
        self.cache = cache_manager
        
        # Configuración global de OSMnx para evitar bloqueos de la API
        ox.settings.timeout = 180
        ox.settings.use_cache = False # Apagamos el caché de osmnx porque usamos el nuestro, más seguro

    def _cells_to_polygon(self, cells: List[str]) -> Polygon:
        """Convierte una lista de hexágonos H3 en un único polígono continuo."""
        if not cells:
            return None
        polys = []
        for cell in cells:
            boundary = h3.cell_to_boundary(cell)
            lon_lat = [(lon, lat) for lat, lon in boundary]
            polys.append(Polygon(lon_lat))
        return unary_union(polys)

    def get_or_build_graph(self, origin: RouteEndpoint, dest: RouteEndpoint, mode: str = "truck") -> nx.MultiDiGraph:
        """Flujo principal: Intenta cargar de caché, si no, descarga de OSM, compone y guarda."""
        
        # 1. Intentar cargar del caché (mapeamos parameters a la nueva firma del cache_manager)
        logger.info("Buscando ruta en caché: %s -> %s", origin.name, dest.name)
        cached_graph = self.cache.load_graph(
            origin=origin.name, 
            dest=dest.name, 
            zoom=self.config.resolution, 
            profile=self.config.buffer_rings, 
            mode=mode
        )
        
        if cached_graph is not None:
            logger.info("✅ ¡Caché Hit! Grafo cargado instantáneamente desde el disco.")
            return cached_graph
            
        logger.info("⚠️ Caché Miss. Iniciando descarga (Smart Lazy Loading)...")
        
        # 2. Matemáticas: Calcular Corredor H3
        corridor = build_h3_corridor(
            origin, dest, 
            resolution=self.config.resolution, 
            buffer_rings=self.config.buffer_rings, 
            max_cells=self.config.max_cells
        )
        
        loc_o_cells, loc_d_cells, trunk_cells = split_cells(
            corridor.buffered_cells, 
            corridor.origin_cell, 
            corridor.destination_cell, 
            local_rings=self.config.local_rings
        )
        
        # 3. Geometría: Crear Polígonos de Descarga
        poly_origen = self._cells_to_polygon(loc_o_cells)
        poly_destino = self._cells_to_polygon(loc_d_cells)
        poly_troncal = self._cells_to_polygon(trunk_cells)
        
        # 4. Descargas OSMnx
        subgraphs = []
        
        # Filtro logístico argentino: Incluye primary, secondary y trunk
        trunk_filter = '["highway"~"motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link"]'
        
        try:
            logger.info("   -> Descargando malla local Origen (%s hexágonos)...", len(loc_o_cells))
            g_origen = ox.graph_from_polygon(poly_origen, network_type="drive", simplify=True)
            subgraphs.append(g_origen)
            
            logger.info("   -> Descargando malla local Destino (%s hexágonos)...", len(loc_d_cells))
            g_destino = ox.graph_from_polygon(poly_destino, network_type="drive", simplify=True)
            subgraphs.append(g_destino)
            
            if poly_troncal is not None and not poly_troncal.is_empty:
                logger.info("   -> Descargando Autopistas Troncales (%s hexágonos). Esto puede tardar...", len(trunk_cells))
                g_troncal = ox.graph_from_polygon(poly_troncal, custom_filter=trunk_filter, simplify=True)
                subgraphs.append(g_troncal)
                
        except Exception as e:
            logger.error("Error crítico durante la descarga de OSMnx: %s", e)
            raise RuntimeError("Fallo al descargar mapas de OpenStreetMap. Revisa tu conexión o los límites de la API.") from e
            
        # 5. Fusión (El Frankenstein)
        logger.info("   -> Fusionando los mapas descargados...")
        final_graph = nx.compose_all(subgraphs)
        
        # Limpieza de topología: Borrar nodos que hayan quedado sueltos en las costuras
        final_graph = ox.utils_graph.remove_isolated_nodes(final_graph)
        
        # 6. Guardar en Caché Seguro
        logger.info("   -> Guardando en caché para futuros usos...")
        self.cache.save_graph(
            graph=final_graph,
            origin=origin.name,
            dest=dest.name,
            zoom=self.config.resolution,
            profile=self.config.buffer_rings,
            mode=mode
        )
        
        return final_graph
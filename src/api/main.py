#main.py
import time
import math
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request

from src.api.schemas import RouteRequest, RouteResponse, ParetoResult
from src.bloque1.h3_router import build_h3_corridor
from src.bloque1.duckdb_ingestor import extract_subgraph_edges, get_nearest_node_osm_id
from src.bloque1.graph_builder import build_directed_graph
from src.bloque2.graph_adapter import get_matrices
from src.bloque3.bayesian_judge import BayesianJudge
from src.bloque4.weight_builder import build_pareto_edges
from src.bloque4.rx_adapter import build_legacy_graph, get_rx_idx_for_osm
from src.bloque4.multiobjective_engine import MultiObjectiveEngine
from src.bloque4.pareto import ParetoFrontResult
import duckdb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PrimeAPI")

# Parquet Files Path Setup
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "parquet_db"
EDGES_PATH = DATA_DIR / "edges.parquet"
NODES_PATH = DATA_DIR / "nodes.parquet"
PRIORS_PATH = DATA_DIR / "priors_historicos.parquet"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Instanciar el semáforo DENTRO del loop de eventos activo
    app.state.semaphore = asyncio.Semaphore(3)
    
    # 2. Validar Parquets
    for path in [EDGES_PATH, NODES_PATH, PRIORS_PATH]:
        if not path.exists():
            raise RuntimeError(f"Parquet artifact not found: {path}")
    logger.info("All immutable artifacts validated. Engine is ready.")
    yield
    # Cleanup on shutdown
    logger.info("Engine shutting down.")

app = FastAPI(lifespan=lifespan, title="Prime Logistics Engine V1.4")

@app.post('/route', response_model=RouteResponse)
async def calculate_route(payload: RouteRequest, request: Request):
    # Obtener el semáforo vivo del estado de la aplicación
    semaphore = request.app.state.semaphore
    
    if semaphore.locked():
        raise HTTPException(status_code=429, detail="Server overloaded. At capacity of 3 concurrent requests.")
        
    async with semaphore:
        start_time = time.time()
        
        try:
            # ATENCIÓN AL CAMBIO DE NOMBRE: request de Pydantic ahora es 'payload'
            if not payload.vehicles or not payload.destinations:
                raise HTTPException(status_code=400, detail="Missing vehicles or destinations.")
            
            v = payload.vehicles[0]
            d = payload.destinations[0]
            
            # 1. Nearest-node lookup para origen y destino
            origin_osm = get_nearest_node_osm_id(v.origin_lat, v.origin_lon)
            dest_osm = get_nearest_node_osm_id(d.lat, d.lon)

            # 2. Corredor H3 y extracción DuckDB
            h3_corridor = build_h3_corridor(
                origin_lat=v.origin_lat, origin_lon=v.origin_lon, 
                dest_lat=d.lat, dest_lon=d.lon
            )
            df_edges = extract_subgraph_edges(h3_corridor)
            
            if len(df_edges) > 50000:
                raise HTTPException(status_code=422, detail="Corredor demasiado grande.")
                
            # 3. Construir grafo rustworkx con coordenadas de nodos (solo los del subgrafo)
            subgraph_osm_ids = set(df_edges['u'].unique()) | set(df_edges['v'].unique())
            osm_list = ', '.join(str(int(x)) for x in subgraph_osm_ids)
            df_nodes = duckdb.sql(f"SELECT osm_id, lat, lon FROM read_parquet('{str(NODES_PATH)}') WHERE osm_id IN ({osm_list})").df()
            graph, osm_to_rx, rx_to_osm = build_directed_graph(df_edges, df_nodes=df_nodes)
            
            # 4. Traducir OSM IDs a índices rustworkx
            source_rx = get_rx_idx_for_osm(osm_to_rx, origin_osm)
            target_rx = get_rx_idx_for_osm(osm_to_rx, dest_osm)

            # Fail-Fast si el nodo no está en la red vial del subgrafo
            if source_rx is None or target_rx is None:
                raise HTTPException(
                    status_code=400,
                    detail="El origen o destino no es accesible por la red vial comercial."
                )

            # 5. Matrices NumPy y Bayesian Judge
            edges_idx, C, A, B = get_matrices(graph)
            judge = BayesianJudge(graph)
            
            # 6. Construir grafo legacy para el motor multiobjetivo
            legacy_graph, config, node_coords = build_legacy_graph(
                rx_graph=graph,
                rx_to_osm=rx_to_osm,
                judge=judge,
                source_rx_idx=source_rx,
                target_rx_idx=target_rx
            )

            # 7. Motor multiobjetivo A*-guiado
            engine = MultiObjectiveEngine(eps_1=0.1, eps_2=50.0, max_total_labels=150000)
            frontier_labels = engine.solve(legacy_graph, str(source_rx), str(target_rx), node_coords=node_coords)

            if not frontier_labels:
                raise HTTPException(status_code=404, detail="No se encontraron rutas viables.")

            # 8. Extraer arquetipos de Pareto
            pareto_result = ParetoFrontResult.from_labels(frontier_labels, engine)

            archetipos = {
                "tanque": pareto_result.extract_tank(),
                "apostador": pareto_result.extract_gambler(),
                "equilibrista": pareto_result.extract_tightrope(),
                "unicornio": pareto_result.extract_unicorn(),
            }

            # 9. Construir respuesta
            pareto_solutions = []
            for archetype_name, sol in archetipos.items():
                if sol is None:
                    continue
                confidence = math.exp(-sol.w_survival)
                pareto_solutions.append(ParetoResult(
                    archetype=archetype_name,
                    w_survival=sol.w_survival,
                    w_expected_cost=sol.w_expected_cost,
                    route_nodes=list(sol.path),
                    confidence=confidence
                ))
            
            proc_time_ms = (time.time() - start_time) * 1000
            
            return RouteResponse(
                processing_time_ms=proc_time_ms,
                total_edges=len(df_edges),
                pareto_solutions=pareto_solutions
            )
            
        finally:
            try:
                del graph, legacy_graph, df_edges, df_nodes, frontier_labels, judge, node_coords
            except NameError:
                pass

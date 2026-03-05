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
from src.config.settings import load_cost_settings
from src.bloque3.threat_loader import load_h3_threat_matrix

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
    
    import time
    t0 = time.time()
    
    # 2. Build Base Graph (Singleton Graph)
    # Read entire parquets strictly to build the base dict and discard DuckDB handles immediately.
    import duckdb
    import gc
    
    # Using read_parquet in duckdb
    df_edges = duckdb.sql(f"SELECT * FROM read_parquet('{str(EDGES_PATH)}')").df()
    df_nodes = duckdb.sql(f"SELECT * FROM read_parquet('{str(NODES_PATH)}')").df()
    
    app.state.base_graph, app.state.osm_to_rx, app.state.rx_to_osm = build_directed_graph(df_edges, df_nodes=df_nodes)
    
    app.state.judge = BayesianJudge(app.state.base_graph)
    logger.info("BayesianJudge singleton inicializado.")
    
    # 3. Destroy DuckDB resources directly and run garbage collector
    del df_edges
    del df_nodes
    gc.collect()
    
    try:
        import psutil
        import os
        process = psutil.Process(os.getpid())
        ram_mb = process.memory_info().rss / 1024 / 1024
    except ImportError:
        ram_mb = 0.0

    load_time_ms = (time.time() - t0) * 1000
    logger.info(f"Lifespan Singleton Graph loaded in {load_time_ms:.2f} ms")
    logger.info(f"RAM used after load: {ram_mb:.2f} MB")

    app.state.cost_settings = load_cost_settings()
    app.state.threat_matrix = load_h3_threat_matrix()
    logger.info(f"Cost settings loaded: c_km_ars={app.state.cost_settings.c_km_ars}")
    logger.info(f"Threat matrix loaded: {len(app.state.threat_matrix)} hexagons in red zones.")
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

            # 2. Resuelve el perfil económico dinámico
            client_cost_env = request.app.state.cost_settings
            if payload.economic_profile:
                # Actualiza campos que no sean None enviando del cliente
                override_dict = payload.economic_profile.model_dump(exclude_unset=True)
                base_dict = client_cost_env.__dict__.copy()
                base_dict.update(override_dict)
                from src.config.settings import CostSettings
                client_cost_env = CostSettings(**base_dict)

            # 3. Corredor H3 y Filtro Zero-Copy
            h3_corridor = set(build_h3_corridor(
                origin_lat=v.origin_lat, origin_lon=v.origin_lon, 
                dest_lat=d.lat, dest_lon=d.lon
            ))
            
            base_graph = request.app.state.base_graph
            osm_to_rx = request.app.state.osm_to_rx
            rx_to_osm = request.app.state.rx_to_osm
            
            # Buscar source y target
            source_rx = get_rx_idx_for_osm(osm_to_rx, origin_osm)
            target_rx = get_rx_idx_for_osm(osm_to_rx, dest_osm)
            
            allowed_nodes = set()
            for u_rx, v_rx, edge_payload in base_graph.weighted_edge_list():
                if getattr(edge_payload, 'h3_index', None) in h3_corridor:
                    allowed_nodes.add(u_rx)
                    allowed_nodes.add(v_rx)

            if source_rx is not None:
                allowed_nodes.add(source_rx)
            if target_rx is not None:
                allowed_nodes.add(target_rx)

            # Fail-Fast si el nodo no está en la red vial del subgrafo o corridor es inmenso
            if source_rx is None or target_rx is None:
                raise HTTPException(
                    status_code=400,
                    detail="El origen o destino no es accesible por la red vial comercial."
                )
                
            if len(allowed_nodes) > 50000:
                raise HTTPException(status_code=422, detail="Corredor demasiado grande.")
                
            # 5. Bayesian Judge natively reading the base graph
            judge = request.app.state.judge
            
            # 6. Construir proxy legacy (Zero-Copy)
            legacy_graph, config, financial_summary = build_legacy_graph(
                rx_graph=base_graph,
                rx_to_osm=rx_to_osm,
                judge=judge,
                source_rx_idx=source_rx,
                target_rx_idx=target_rx,
                cost_env=client_cost_env,
                allowed_nodes=allowed_nodes
            )
            logger.info(f"Financial summary: {financial_summary}")

            # 7. Motor multiobjetivo A*-guiado
            # Extraemos coordenadas solo del proxy (nodos en allowed_nodes)
            node_coords = {n.node_id: (n.lat, n.lon) for n in legacy_graph.nodes if n.lat != 0.0 or n.lon != 0.0}
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
                total_edges=0, # total_edges attribute meaning changes as we lazily query, we don't return an accurate global sum without looping, so we set it to 0. It is not required to be accurate.
                pareto_solutions=pareto_solutions
            )
            
        finally:
            try:
                del legacy_graph, frontier_labels, node_coords
                gc.collect()
            except NameError:
                pass

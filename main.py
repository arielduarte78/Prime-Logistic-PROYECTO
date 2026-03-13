#src/api/main.py
import time
import math
import asyncio
import logging
import json
import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks, Security
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

# Cargar variables de entorno al inicio
load_dotenv()

from src.api.schemas import RouteRequest, RouteResponse, ParetoResult, FleetRequest, FleetResponse
from src.block5.vrp_orchestrator import calculate_fleet
from src.block5.speed_profile_loader import load_speed_profiles
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
from src.api.security import rate_limit_route, rate_limit_fleet, verify_api_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PrimeAPI")

# Parquet Files Path Setup
DATA_DIR = Path(__file__).resolve().parent / "data" / "parquet_db"
EDGES_PATH = DATA_DIR / "edges.parquet"
NODES_PATH = DATA_DIR / "nodes.parquet"
PRIORS_PATH = DATA_DIR / "priors_historicos.parquet"
AUDIT_LOG_DIR = Path("data/audit_logs")
AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Instanciar el semaforo DENTRO del loop de eventos activo
    app.state.semaphore = asyncio.Semaphore(3)
    app.state.fleet_semaphore = asyncio.Semaphore(1)
    
    import time
    t0 = time.time()
    
    # 2. Build Base Graph (Singleton Graph)
    # Read entire parquets strictly to build the base dict and discard DuckDB handles immediately.
    try:
        import duckdb
        import gc
        
        # Using read_parquet in duckdb
        df_edges = duckdb.sql(f"SELECT * FROM read_parquet('{str(EDGES_PATH)}')").df()
        df_nodes = duckdb.sql(f"SELECT * FROM read_parquet('{str(NODES_PATH)}')").df()
        
        app.state.base_graph, app.state.osm_to_rx, app.state.rx_to_osm = build_directed_graph(df_edges, df_nodes=df_nodes)
        
        app.state.judge = BayesianJudge(app.state.base_graph)
        app.state.judge_standard = app.state.judge  # alias, mismo objeto
        logger.info("BayesianJudge singleton inicializado.")
        
        # --- judge_premium: clon degradado por escenarios estocásticos ---
        stochastic_path = DATA_DIR / "stochastic_priors.parquet"
        if stochastic_path.exists():
            import pandas as pd
            import copy
            df_stochastic = pd.read_parquet(str(stochastic_path))
            judge_premium = copy.deepcopy(app.state.judge_standard)
            n_updated = judge_premium.load_stochastic_overrides(df_stochastic, app.state.osm_to_rx)
            app.state.judge_premium = judge_premium
            logger.info(f"judge_premium instanciado: {n_updated} aristas degradadas por escenarios estocásticos.")
        else:
            app.state.judge_premium = None
            logger.warning("stochastic_priors.parquet no encontrado. judge_premium no disponible.")
        
        # 3. Destroy DuckDB resources directly and run garbage collector
        del df_edges
        del df_nodes
        gc.collect()

        from scipy.spatial import cKDTree
        import numpy as np

        coords = []
        rx_indices = []
        for rx_idx, osm_id in app.state.rx_to_osm.items():
            node = app.state.base_graph[rx_idx]
            if hasattr(node, 'lat') and node.lat != 0.0:
                coords.append((node.lat, node.lon))
                rx_indices.append(rx_idx)

        coords_array = np.array(coords)
        app.state.spatial_index = cKDTree(coords_array)
        app.state.spatial_rx_indices = rx_indices
        logger.info(f"Spatial index built: {len(rx_indices):,} nodes indexed.")

        
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
        app.state.speed_profiles = load_speed_profiles()
        logger.info(f"Cost settings loaded: c_km_ars={app.state.cost_settings.c_km_ars}")
        logger.info(f"Threat matrix loaded: {len(app.state.threat_matrix)} hexagons in red zones.")
        logger.info("speed_profiles loaded into app.state")
    except Exception as e:
        import sys
        logger.error(f"[FATAL] No se pudo cargar la topología AMBA: {e}")
        sys.exit(1)
        
    yield
    # Cleanup on shutdown
    logger.info("Engine shutting down.")

from fastapi.middleware.cors import CORSMiddleware

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(lifespan=lifespan, title="Prime Logistics Engine V1.4", redirect_slashes=False)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS_REGEX = (
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
    r"|https://.*\.vercel\.app"
    r"|https://.*\.hf\.space"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=ALLOWED_ORIGINS_REGEX,
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# Guard: coordenadas fuera del bounding box AMBA
AMBA_BOUNDS = {
    "lat_min": -35.5, "lat_max": -33.5,
    "lon_min": -59.5, "lon_max": -57.5
}

def _validate_coords(lat, lon, label):
    if not (AMBA_BOUNDS["lat_min"] <= lat <= AMBA_BOUNDS["lat_max"] and
            AMBA_BOUNDS["lon_min"] <= lon <= AMBA_BOUNDS["lon_max"]):
        raise HTTPException(
            status_code=400,
            detail=f"{label} fuera del área de cobertura AMBA."
        )

# Guard: origen == destino
def _validate_not_same(origin_lat, origin_lon, dest_lat, dest_lon):
    if abs(origin_lat - dest_lat) < 1e-6 and abs(origin_lon - dest_lon) < 1e-6:
        raise HTTPException(
            status_code=400,
            detail="Origen y destino son idénticos."
        )

def _write_audit_log(
    endpoint: str,
    request_payload: dict,
    response_payload: dict,
    api_key_hash: str,
    processing_ms: float
) -> None:
    """
    Escribe registro forense inmutable a disco.
    Diseñado para ser llamado en background sin bloquear el response.
    El hash SHA-256 del payload permite detectar manipulación posterior.
    """
    try:
        payload_str = json.dumps(request_payload, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "api_key_hash": api_key_hash,
            "processing_ms": round(processing_ms, 2),
            "payload_sha256": payload_hash,
            "request": request_payload,
            "response_summary": {
                "total_time_ms": response_payload.get("total_time_ms"),
                "time_windows_enforced": response_payload.get("time_windows_enforced"),
                "shift_limit_enforced": response_payload.get("shift_limit_enforced"),
                "toll_fallback_edges": response_payload.get("toll_fallback_edges", 0),
                "phase4_total_legs": response_payload.get("phase4_total_legs"),
                "archetypes_computed": list(response_payload.get("plans", {}).keys()),
                "uncovered_per_archetype": {
                    arch: [d["id"] for d in plan.get("uncovered", [])]
                    for arch, plan in response_payload.get("plans", {}).items()
                    if isinstance(plan, dict) and "uncovered" in plan
                }
            }
        }
        
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = AUDIT_LOG_DIR / f"{date_str}.jsonl"
        
        with open(filename, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
            
    except Exception as e:
        logger.error(f"Audit log write failed: {e}")

@app.post('/fleet', response_model=FleetResponse)
@app.post('/fleet/', response_model=FleetResponse)
@limiter.limit("10/minute;100/hour")
async def fleet_endpoint(
    payload: FleetRequest, 
    request: Request,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    semaphore = request.app.state.fleet_semaphore
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=429, detail="Server overloaded. At capacity.")
        
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: calculate_fleet(payload, request)
        )
        if asyncio.iscoroutine(result):
            result = await result
            
        background_tasks.add_task(
            _write_audit_log,
            endpoint="/fleet",
            request_payload=payload.model_dump(),
            response_payload=result.model_dump(),
            api_key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
            processing_ms=result.total_time_ms
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Excepción no controlada en /fleet: {e}", exc_info=True)
        raise HTTPException(status_code=422, detail=f"Error procesando la solicitud: {str(e)}")
    finally:
        semaphore.release()

@app.post('/route', response_model=RouteResponse)
@app.post('/route/', response_model=RouteResponse)
@limiter.limit("10/minute;100/hour")
async def calculate_route(
    payload: RouteRequest, 
    request: Request,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    # Obtener el semaforo vivo del estado de la aplicacion
    semaphore = request.app.state.semaphore
    
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=429, detail="Server overloaded. At capacity of 3 concurrent requests.")
        
    try:
        start_time = time.time()
        
        # ATENCION AL CAMBIO DE NOMBRE: request de Pydantic ahora es 'payload'
        if not payload.vehicles or not payload.destinations:
            raise HTTPException(status_code=400, detail="Missing vehicles or destinations.")
        
        v = payload.vehicles[0]
        d = payload.destinations[0]
        
        # Validations (Guards)
        _validate_coords(v.origin_lat, v.origin_lon, "Origen")
        _validate_coords(d.lat, d.lon, "Destino")
        _validate_not_same(v.origin_lat, v.origin_lon, d.lat, d.lon)
        
        # 1. Nearest-node lookup para origen y destino
        origin_osm = get_nearest_node_osm_id(v.origin_lat, v.origin_lon)
        dest_osm = get_nearest_node_osm_id(d.lat, d.lon)

        # 2. Resuelve el perfil economico dinamico
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

        # Fail-Fast si el nodo no esta en la red vial del subgrafo o corridor es inmenso
        if source_rx is None or target_rx is None:
            raise HTTPException(
                status_code=400,
                detail="El origen o destino no es accesible por la red vial comercial."
            )
            
        if len(allowed_nodes) > 50000:
            raise HTTPException(status_code=422, detail="Corredor demasiado grande.")
            
        # 5. Bayesian Judge — selección standard vs premium
        judge = request.app.state.judge_premium if (
            payload.stochastic_mode and request.app.state.judge_premium is not None
        ) else request.app.state.judge_standard
        
        # 5b. Resolver departure_hour para trafico dinamico
        if payload.departure_time:
            try:
                departure_hour = datetime.fromisoformat(payload.departure_time).hour
            except (ValueError, TypeError):
                try:
                    departure_hour = datetime.strptime(payload.departure_time, "%H:%M").hour
                except (ValueError, TypeError):
                    departure_hour = datetime.now(tz=ZoneInfo("America/Argentina/Buenos_Aires")).hour
        else:
            departure_hour = datetime.now(tz=ZoneInfo("America/Argentina/Buenos_Aires")).hour
        
        speed_profiles = request.app.state.speed_profiles
        logger.info(f"departure_hour resolved to {departure_hour}")
        
        fallback_counter = [0]
        # 6. Construir proxy legacy (Zero-Copy)
        legacy_graph, config, financial_summary = build_legacy_graph(
            rx_graph=base_graph,
            rx_to_osm=rx_to_osm,
            judge=judge,
            source_rx_idx=source_rx,
            target_rx_idx=target_rx,
            cost_env=client_cost_env,
            allowed_nodes=allowed_nodes,
            departure_hour=departure_hour,
            speed_profiles=speed_profiles,
            fallback_counter=fallback_counter
        )
        logger.info(f"Financial summary: {financial_summary}")

        # 7. Motor multiobjetivo A*-guiado
        # Extraemos coordenadas solo del proxy (nodos en allowed_nodes)
        node_coords = {n.node_id: (n.lat, n.lon) for n in legacy_graph.nodes if n.lat != 0.0 or n.lon != 0.0}
        engine = MultiObjectiveEngine(eps_1=0.1, eps_2=50.0, max_total_labels=150000)
        frontier_labels = await asyncio.get_event_loop().run_in_executor(
            None, lambda: engine.solve(legacy_graph, str(source_rx), str(target_rx), node_coords=node_coords)
        )

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
        
        soluciones_validas = [s for s in archetipos.values() if s is not None]
        if soluciones_validas:
            w_min = min(s.w_survival for s in soluciones_validas)
            w_max = max(s.w_survival for s in soluciones_validas)
            def normalize_confidence(w_survival):
                if w_max == w_min:
                    return 100.0
                return round(100.0 * (w_max - w_survival) / (w_max - w_min), 1)
        else:
            normalize_confidence = lambda x: 0.0

        for archetype_name, sol in archetipos.items():
            if sol is None:
                continue
                
            coords = []
            for node_id in sol.path:
                rx_idx = int(node_id)
                node_payload = request.app.state.base_graph[rx_idx]
                if hasattr(node_payload, 'lat') and node_payload.lat != 0.0:
                    coords.append([node_payload.lat, node_payload.lon])
                    
            confidence = normalize_confidence(sol.w_survival)
            pareto_solutions.append(ParetoResult(
                archetype=archetype_name,
                w_survival=sol.w_survival,
                w_expected_cost=sol.w_expected_cost,
                route_nodes=list(sol.path),
                route_coordinates=coords,
                confidence=confidence
            ))
        
        proc_time_ms = (time.time() - start_time) * 1000
        
        result = RouteResponse(
            processing_time_ms=proc_time_ms,
            total_edges=0, # total_edges attribute meaning changes as we lazily query, we don't return an accurate global sum without looping, so we set it to 0. It is not required to be accurate.
            toll_fallback_edges=fallback_counter[0],
            pareto_solutions=pareto_solutions
        )
        
        background_tasks.add_task(
            _write_audit_log,
            endpoint="/route",
            request_payload=payload.model_dump(),
            response_payload=result.model_dump(),
            api_key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
            processing_ms=proc_time_ms
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Excepción no controlada en /route: {e}", exc_info=True)
        raise HTTPException(status_code=422, detail=f"Error procesando la solicitud: {str(e)}")
    finally:
        try:
            del legacy_graph, frontier_labels, node_coords
            gc.collect()
        except NameError:
            pass
        semaphore.release()

@app.get("/health")
@app.get("/health/")
async def health():
    graph_ok = hasattr(app.state, "base_graph") and app.state.base_graph is not None
    return {
        "status": "ok" if graph_ok else "loading",
        "graph_nodes": len(app.state.rx_to_osm) if graph_ok else 0,
        "version": "Abbey 1.5",
        "ckm_ars": 807.85,
        "ch_ars": 19130.79
    }

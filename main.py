#src/api/main.py
import base64
import os
import time
import math
import asyncio
import logging
import json
import hashlib
import hmac
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks, Security
from fastapi.responses import ORJSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

# Cargar variables de entorno al inicio
load_dotenv()

from src.api.schemas import (
    RouteRequest, RouteResponse, ParetoResult, FleetRequest, FleetResponse,
    TokenRequest, TokenResponse, RefreshResponse, EconomicProfile,
)
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
from src.config.settings import load_cost_settings, resolve_profile, costo_por_km, costo_por_hora
from src.bloque3.threat_loader import load_h3_threat_matrix
from src.bloque3.integrity_chain import IntegrityChain
from src.api.cola import Cola
from src.api.security import rate_limit_route, rate_limit_fleet, verify_api_key
from src.api.identity import (
    configure_identity, sanitize_secrets, get_current_identity,
    require_role, track_usage, create_access_token, create_refresh_token,
    validate_refresh_token, get_usage_report, configure_usage_persistence,
    force_persist_usage, TokenPayload, _authorized_keys,
)

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
    # 1. Colas de espera (dentro del loop de eventos activo).
    #    /fleet: 1 cálculo a la vez (en el CPU gratis un /fleet de 2 camiones y 4 destinos tarda ~30 s),
    #    hasta 3 esperando y como mucho 90 s de espera. /route es liviano (~1 s): 3 a la vez.
    app.state.cola_fleet = Cola(en_paralelo=1, max_en_espera=3, espera_max_s=90)
    app.state.cola_route = Cola(en_paralelo=3, max_en_espera=10, espera_max_s=30)
    
    import time
    t0 = time.time()
    
    # ─── ISO 27001 A.12.4: Carga de clave HMAC para IntegrityChain ───
    hmac_key_b64 = os.environ.get("ABBEY_HMAC_KEY")
    if hmac_key_b64:
        try:
            hmac_key = base64.b64decode(hmac_key_b64)
            integrity_chain = IntegrityChain(hmac_key)
            logger.info("HMAC key loaded from ABBEY_HMAC_KEY env var.")
        except Exception as e:
            logger.error(f"Failed to decode ABBEY_HMAC_KEY: {e}. Generating ephemeral key.")
            hmac_key = os.urandom(32)
            integrity_chain = IntegrityChain(hmac_key)
    else:
        logger.warning(
            "SECURITY WARNING: ABBEY_HMAC_KEY not set. "
            "Generating ephemeral key for DEV mode. "
            "DO NOT USE IN PRODUCTION."
        )
        hmac_key = os.urandom(32)
        integrity_chain = IntegrityChain(hmac_key)
    
    app.state.integrity_chain = integrity_chain
    
    # ─── ISO 27001 A.9/A.10: Carga de secreto JWT para Identity ───
    jwt_secret_b64 = os.environ.get("ABBEY_JWT_SECRET")
    if jwt_secret_b64:
        try:
            jwt_secret = base64.b64decode(jwt_secret_b64)
            logger.info("JWT secret loaded from ABBEY_JWT_SECRET env var.")
        except Exception as e:
            logger.error(f"Failed to decode ABBEY_JWT_SECRET: {e}. Generating ephemeral.")
            jwt_secret = os.urandom(32)
    else:
        logger.warning(
            "SECURITY WARNING: ABBEY_JWT_SECRET not set. "
            "Generating ephemeral JWT secret for DEV mode."
        )
        jwt_secret = os.urandom(32)
    
    jwt_secret_prev_b64 = os.environ.get("ABBEY_JWT_SECRET_PREV")
    jwt_secret_prev = base64.b64decode(jwt_secret_prev_b64) if jwt_secret_prev_b64 else None
    
    # Load legacy API keys for backward-compatible auth
    from src.api.security import _load_authorized_keys
    legacy_keys = _load_authorized_keys()
    
    configure_identity(
        jwt_secret=jwt_secret,
        jwt_secret_prev=jwt_secret_prev,
        authorized_keys=legacy_keys,
        access_ttl=int(os.environ.get("ABBEY_ACCESS_TOKEN_TTL", "900")),
        refresh_ttl=int(os.environ.get("ABBEY_REFRESH_TOKEN_TTL", "604800")),
    )
    
    # CISO FIX #1: Configure usage persistence to JSONL
    configure_usage_persistence(
        persist_dir=Path("data/audit_logs"),
        interval_seconds=int(os.environ.get("ABBEY_USAGE_PERSIST_INTERVAL", "60")),
    )
    
    # 2. Build Base Graph (Singleton Graph)
    # Read entire parquets strictly to build the base dict and discard DuckDB handles immediately.
    try:
        import duckdb
        import gc
        
        # Using read_parquet in duckdb
        df_edges = duckdb.sql(f"SELECT * FROM read_parquet('{str(EDGES_PATH)}')").df()
        df_nodes = duckdb.sql(f"SELECT * FROM read_parquet('{str(NODES_PATH)}')").df()
        
        app.state.base_graph, app.state.osm_to_rx, app.state.rx_to_osm = build_directed_graph(df_edges, df_nodes=df_nodes)
        
        # ─── Bloque 2: Pre-computar base network para Monte Carlo dinámico ───
        from src.bloque2.graph_adapter import get_matrices, build_network_snapshot_from_rx
        app.state.mc_matrices = get_matrices(app.state.base_graph)
        app.state.mc_network_snapshot = build_network_snapshot_from_rx(app.state.base_graph)
        
        app.state.judge = BayesianJudge(app.state.base_graph, integrity_chain=integrity_chain)
        app.state.judge_standard = app.state.judge  # alias, mismo objeto
        logger.info("BayesianJudge singleton inicializado con IntegrityChain.")
        
        # --- judge_premium: clon pre-calculado por escenarios estocásticos fijos ---
        stochastic_path = DATA_DIR / "stochastic_priors.parquet"
        if stochastic_path.exists():
            import pandas as pd
            df_stochastic = pd.read_parquet(str(stochastic_path))
            judge_premium = app.state.judge_standard.spawn_ephemeral_clone()
            # El clon efímero hereda la misma IntegrityChain instance (shared)
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
    # Cleanup on shutdown — ISO 27001: sanitizar claves de memoria
    force_persist_usage()  # CISO FIX #1: persist counters before shutdown
    if hasattr(app.state, 'integrity_chain') and app.state.integrity_chain:
        app.state.integrity_chain.sanitize_key()
    sanitize_secrets()  # Zero JWT secrets in memory
    logger.info("Engine shutting down. HMAC + JWT keys sanitized. Usage persisted.")

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
    client_id: str,
    client_name: str,
    client_role: str,
    processing_ms: float
) -> None:
    """
    Escribe registro forense inmutable a disco.
    Diseñado para ser llamado en background sin bloquear el response.
    El hash SHA-256 del payload permite detectar manipulación posterior.
    Fase 2: Enriquecido con identidad del cliente para facturación.
    """
    try:
        payload_str = json.dumps(request_payload, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "client_id": client_id,
            "client_name": client_name,
            "client_role": client_role,
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

@app.post('/fleet', response_model=FleetResponse, response_class=ORJSONResponse)
@app.post('/fleet/', response_model=FleetResponse, response_class=ORJSONResponse)
@limiter.limit("10/minute;100/hour")
async def fleet_endpoint(
    payload: FleetRequest, 
    request: Request,
    background_tasks: BackgroundTasks,
    identity: TokenPayload = Depends(require_role("operator", "admin")),
):
    # Espera su turno en la cola (en vez de rebotar al instante). El turno se libera siempre.
    async with request.app.state.cola_fleet.turno():
        return await _procesar_fleet(payload, request, background_tasks, identity)


async def _procesar_fleet(payload, request, background_tasks, identity):
    try:
        # calculate_fleet es async: las partes pesadas por arquetipo corren en hilos adentro.
        result = await calculate_fleet(payload, request)
        
        # ─── CISO Directive: Propagar flag de integridad al cliente ───
        judge = request.app.state.judge_premium if (
            payload.stochastic_mode and getattr(request.app.state, 'judge_premium', None) is not None
        ) else request.app.state.judge_standard
        if judge and getattr(judge, 'integrity_compromised', False):
            result.integrity_compromised = True
            logger.critical(
                "INTEGRITY COMPROMISED FLAG SET on /fleet response. "
                "Routes calculated with conservative priors."
            )
            
        background_tasks.add_task(
            _write_audit_log,
            endpoint="/fleet",
            request_payload=payload.model_dump(),
            response_payload=result.model_dump(),
            client_id=identity.client_id,
            client_name=identity.client_name,
            client_role=identity.role,
            processing_ms=result.total_time_ms
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Excepción no controlada en /fleet: {e}", exc_info=True)
        raise HTTPException(status_code=422, detail=f"Error procesando la solicitud: {str(e)}")

@app.post('/route', response_model=RouteResponse, response_class=ORJSONResponse)
@app.post('/route/', response_model=RouteResponse, response_class=ORJSONResponse)
@limiter.limit("10/minute;100/hour")
async def calculate_route(
    payload: RouteRequest, 
    request: Request,
    background_tasks: BackgroundTasks,
    identity: TokenPayload = Depends(require_role("operator", "admin")),
):
    # Espera su turno en la cola (en vez de rebotar al instante). El turno se libera siempre.
    async with request.app.state.cola_route.turno():
        return await _procesar_route(payload, request, background_tasks, identity)


async def _procesar_route(payload, request, background_tasks, identity):
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

        # 2. Perfil economico: YAML + lo que mande el cliente (igual que /fleet)
        client_cost_env = resolve_profile(payload.economic_profile)

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
            client_id=identity.client_id,
            client_name=identity.client_name,
            client_role=identity.role,
            processing_ms=proc_time_ms
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Excepción no controlada en /route: {e}", exc_info=True)
        raise HTTPException(status_code=422, detail=f"Error procesando la solicitud: {str(e)}")

def _leer_commit(raiz: Path = Path(__file__).resolve().parent) -> str:
    """Hash del commit que está corriendo: variable GIT_COMMIT, o se lee de la carpeta .git (sin usar el comando git)."""
    desde_entorno = os.environ.get("GIT_COMMIT")
    if desde_entorno:
        return desde_entorno.strip()
    try:
        git = raiz / ".git"
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head  # HEAD desacoplado: ya es el hash
        ref = head[5:]
        archivo_ref = git / ref
        if archivo_ref.exists():
            return archivo_ref.read_text().strip()
        for linea in (git / "packed-refs").read_text().splitlines():
            if linea.endswith(" " + ref):
                return linea.split()[0]
    except OSError:
        pass
    return "desconocido"

COMMIT = _leer_commit()

@app.get("/health")
@app.get("/health/")
async def health():
    graph_ok = hasattr(app.state, "base_graph") and app.state.base_graph is not None
    perfil = resolve_profile(None)
    return {
        "status": "ok" if graph_ok else "loading",
        "graph_nodes": len(app.state.rx_to_osm) if graph_ok else 0,
        "version": "Abbey 1.5",
        "commit": COMMIT,
        "ckm_ars": round(costo_por_km(perfil), 2),
        "ch_ars": round(costo_por_hora(perfil), 2),
    }

# ─────────────────────────────────────────────────────────
# AUTH ENDPOINTS (Fase 2 SGSI — A.9, A.10)
# ─────────────────────────────────────────────────────────

# Client registry — loaded from ABBEY_CLIENT_REGISTRY env var
# Format: "client_id:client_secret:client_name:role,..."
def _load_client_registry() -> dict:
    """Load registered clients from environment variable."""
    registry_str = os.environ.get("ABBEY_CLIENT_REGISTRY", "")
    if not registry_str:
        logger.warning(
            "ABBEY_CLIENT_REGISTRY not set. /auth/token rechaza todo "
            "(la clave x-api-key sigue funcionando)."
        )
        return {}
    registry = {}
    for entry in registry_str.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 4:
            cid, secret, name, role = parts[0], parts[1], parts[2], parts[3]
            registry[cid.strip()] = {
                "secret": secret.strip(),
                "name": name.strip(),
                "role": role.strip(),
            }
    return registry

_client_registry = _load_client_registry()


@app.post("/auth/token", response_model=TokenResponse)
async def auth_token(req: TokenRequest):
    """
    Issue JWT access + refresh tokens.
    No authentication required — uses client credentials (client_id + client_secret).
    """
    client = _client_registry.get(req.client_id)
    # Siempre se compara (aunque el cliente no exista) y con el mismo mensaje de error:
    # asi no se puede adivinar que client_id existen ni medir tiempos de respuesta.
    secreto_esperado = client["secret"] if client else ""
    secreto_ok = hmac.compare_digest(req.client_secret.encode("utf-8"), secreto_esperado.encode("utf-8"))
    if not client or not secreto_ok:
        logger.warning("AUTH FAILED: invalid secret for client=%s", req.client_id)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access = create_access_token(req.client_id, client["name"], client["role"])
    refresh = create_refresh_token(req.client_id, client["name"], client["role"])
    
    return TokenResponse(
        access_token=access,
        expires_in=int(os.environ.get("ABBEY_ACCESS_TOKEN_TTL", "900")),
        refresh_token=refresh,
    )


@app.post("/auth/refresh", response_model=RefreshResponse)
async def auth_refresh(request: Request):
    """
    Refresh an access token using a valid refresh token.
    Refresh token must be sent as Bearer in Authorization header.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing refresh token")
    
    refresh_token = auth_header[7:]
    identity = validate_refresh_token(refresh_token)
    
    new_access = create_access_token(
        identity.client_id, identity.client_name, identity.role
    )
    
    return RefreshResponse(
        access_token=new_access,
        expires_in=int(os.environ.get("ABBEY_ACCESS_TOKEN_TTL", "900")),
    )


@app.get("/admin/usage")
async def admin_usage(
    identity: TokenPayload = Depends(require_role("admin")),
):
    """Usage report per client — admin only. Pay-per-Request foundation."""
    return get_usage_report()

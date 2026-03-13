# src/block5/vrp_orchestrator.py

import time

import logging

from datetime import datetime

from zoneinfo import ZoneInfo

from typing import Dict, List, Any

from fastapi import HTTPException

import math

import asyncio

from concurrent.futures import ThreadPoolExecutor



from src.api.schemas import FleetRequest, FleetResponse, ParetoResult

from src.block5.cost_matrix_builder import build_dense_cost_matrix

from src.block5.vrp_solver import solve_vrp

from src.bloque1.duckdb_ingestor import get_nearest_node_osm_id

from src.bloque4.rx_adapter import get_rx_idx_for_osm, build_legacy_graph

from src.bloque4.multiobjective_engine import MultiObjectiveEngine

from src.bloque4.pareto import ParetoFrontResult



logger = logging.getLogger("VRP_Orchestrator")



# Thread pool dedicado para paralelización de arquetipos

# max_workers=4 porque nunca hay más de 4 arquetipos simultáneos

_archetype_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="archetype")



def _compute_archetype_plan(
    archetype: str,
    base_graph,
    nodes_of_interest: list,
    client_cost_env,
    threat_matrix: dict,
    judge,
    osm_to_rx: dict,
    rx_to_osm: dict,
    shared_time_matrix: list,
    time_windows: list,
    has_real_windows: bool,
    service_times: list,
    max_shift_per_vehicle: list,
    payload,
    spatial_index,
    spatial_rx_indices,
    departure_hour: int,
    speed_profiles: dict,
    p2_subgraph_nodes: set,
    shift_start_minutes: int = 480,
    departure_time: str = None
) -> tuple:
    """
    Función sincrónica pura para un arquetipo.
    Retorna (archetype, plan_dict, legs_count, fallback_count).
    Diseñada para correr en ThreadPoolExecutor.
    """
    fallback_counter = [0]
    # Phase 2
    t0_p2 = time.time()
    cost_matrix, _ = build_dense_cost_matrix(
        base_graph, nodes_of_interest, archetype,
        client_cost_env, threat_matrix,
        judge, osm_to_rx,
        departure_hour=departure_hour,
        speed_profiles=speed_profiles,
        precomputed_time_matrix=shared_time_matrix,
        node_filter=p2_subgraph_nodes,
        fallback_counter=fallback_counter
    )
    p2_time = time.time() - t0_p2



    # Phase 3

    t0_p3 = time.time()

    num_vehicles = sum(1 for _ in payload.vehicles)

    capacities = [v.capacity_tons for v in payload.vehicles]

    demands = [0.0] * num_vehicles + [d.demand_tons for d in payload.destinations]



    result = solve_vrp(

        cost_matrix=cost_matrix,

        vehicle_capacities=capacities,

        demands=demands,

        num_vehicles=num_vehicles,

        time_limit_seconds=payload.time_limit_seconds,

        time_matrix=shared_time_matrix,

        time_windows=time_windows if has_real_windows else None,

        service_times=service_times,

        max_shift_minutes_per_vehicle=max_shift_per_vehicle

    )

    p3_time = time.time() - t0_p3



    if not result:

        return archetype, {"error": "No viable fleet assignment found."}, 0



    routes, schedules = result

    V_rx_count = num_vehicles



    plan = []

    assigned_dest_indices = set()

    for v_idx, (route, schedule) in enumerate(zip(routes, schedules)):

        v_destinations = []

        v_schedule = []
        last_arrival_min = 0

        for step_idx, node_idx in enumerate(route):

            if node_idx >= V_rx_count:

                d_idx = node_idx - V_rx_count

                dest = payload.destinations[d_idx]

                v_destinations.append(dest)

                assigned_dest_indices.add(d_idx)

                if step_idx < len(schedule):

                    smin = schedule[step_idx]["suggested_arrival_min"]
                    # Fracture 1: apply shift offset
                    abs_min = (smin + shift_start_minutes) if smin is not None else None

                    v_schedule.append({

                        "destination_id": dest.id,

                        "suggested_arrival_min": abs_min,

                        "earliest_arrival_min": (schedule[step_idx]["earliest_arrival_min"] + shift_start_minutes) if schedule[step_idx]["earliest_arrival_min"] is not None else None,

                        "latest_arrival_min": (schedule[step_idx]["latest_arrival_min"] + shift_start_minutes) if schedule[step_idx]["latest_arrival_min"] is not None else None,

                        "suggested_arrival_hhmm": (

                            f"{abs_min // 60:02d}:{abs_min % 60:02d}" if abs_min is not None else None

                        )

                    })
                    if smin is not None:
                        last_arrival_min = smin

        # Fracture 2: return-to-base
        if v_destinations and len(route) >= 2:
            last_node_idx = route[-2] if route[-1] < V_rx_count else route[-1]
            depot_idx = v_idx  # vehicle's own depot
            if last_node_idx < len(shared_time_matrix) and depot_idx < len(shared_time_matrix[last_node_idx]):
                return_travel = shared_time_matrix[last_node_idx][depot_idx]
                if return_travel is not None and return_travel < 99999:
                    last_dest_service = int(v_destinations[-1].service_time_min) if v_destinations else 0
                    return_min = last_arrival_min + last_dest_service + int(return_travel)
                    abs_return = return_min + shift_start_minutes
                    v_schedule.append({
                        "destination_id": "__RETURN_BASE__",
                        "is_return": True,
                        "suggested_arrival_min": abs_return,
                        "earliest_arrival_min": None,
                        "latest_arrival_min": None,
                        "suggested_arrival_hhmm": f"{abs_return // 60:02d}:{abs_return % 60:02d}"
                    })

        plan.append({

            "vehicle": payload.vehicles[v_idx],

            "route_destinations": v_destinations,

            "route_indices": route,

            "schedule": v_schedule

        })



    uncovered = [payload.destinations[i] for i in range(len(payload.destinations)) if i not in assigned_dest_indices]



    # Phase 4

    legs_evaluations = []

    legs_count = 0

    for v_plan in plan:

        r_indices = v_plan["route_indices"]

        for step in range(len(r_indices) - 1):

            source_idx = r_indices[step]

            target_idx = r_indices[step + 1]

            if source_idx == target_idx:

                continue

            s_rx = nodes_of_interest[source_idx]

            t_rx = nodes_of_interest[target_idx]

            s_node = base_graph[s_rx]

            t_node = base_graph[t_rx]

            lat_center = (s_node.lat + t_node.lat) / 2

            lon_center = (s_node.lon + t_node.lon) / 2

            diagonal = math.sqrt((s_node.lat - t_node.lat)**2 + (s_node.lon - t_node.lon)**2)

            seg_radius = max(diagonal * 0.6, 0.05)

            seg_candidates = spatial_index.query_ball_point([lat_center, lon_center], seg_radius)

            segment_nodes = set(spatial_rx_indices[i] for i in seg_candidates)

            segment_nodes.add(s_rx)

            segment_nodes.add(t_rx)



            legacy_graph, config, _ = build_legacy_graph(
                rx_graph=base_graph,
                rx_to_osm=rx_to_osm,
                judge=judge,
                source_rx_idx=s_rx,
                target_rx_idx=t_rx,
                cost_env=client_cost_env,
                allowed_nodes=segment_nodes,
                departure_hour=departure_hour,
                speed_profiles=speed_profiles,
                fallback_counter=fallback_counter
            )



            node_coords = {n.node_id: (n.lat, n.lon) for n in legacy_graph.nodes if n.lat != 0.0 or n.lon != 0.0}

            engine = MultiObjectiveEngine(eps_1=0.1, eps_2=50.0, max_total_labels=150000)

            frontier_labels = engine.solve(legacy_graph, str(s_rx), str(t_rx), node_coords=node_coords)



            if frontier_labels:

                pareto_result = ParetoFrontResult.from_labels(frontier_labels, engine)

                archetipos_inner = {

                    "tanque": pareto_result.extract_tank(),

                    "apostador": pareto_result.extract_gambler(),

                    "equilibrista": pareto_result.extract_tightrope(),

                    "unicornio": pareto_result.extract_unicorn(),

                }

                leg_sols = []

                soluciones_validas = [s for s in archetipos_inner.values() if s is not None]

                if soluciones_validas:

                    w_min = min(s.w_survival for s in soluciones_validas)

                    w_max = max(s.w_survival for s in soluciones_validas)

                    def normalize_confidence(w_survival, w_min=w_min, w_max=w_max):

                        if w_max == w_min:

                            return 100.0

                        return round(100.0 * (w_max - w_survival) / (w_max - w_min), 1)

                else:

                    normalize_confidence = lambda x: 0.0



                for arch_name, sol in archetipos_inner.items():

                    if sol:

                        coords = []

                        for node_id in sol.path:

                            rx_idx = int(node_id)

                            node_payload = base_graph[rx_idx]

                            if hasattr(node_payload, 'lat') and node_payload.lat != 0.0:

                                coords.append([node_payload.lat, node_payload.lon])

                        leg_sols.append(ParetoResult(

                            archetype=arch_name,

                            w_survival=sol.w_survival,

                            w_expected_cost=sol.w_expected_cost,

                            route_nodes=list(sol.path),

                            route_coordinates=coords,

                            confidence=normalize_confidence(sol.w_survival)

                        ))



                legs_evaluations.append({

                    "source_osm": rx_to_osm[s_rx],

                    "target_osm": rx_to_osm[t_rx],

                    "pareto_solutions": leg_sols

                })

                legs_count += 1



    # Fracture 3: aggregate costs and reasoning from Pareto segments
    total_w_survival = 0.0
    total_w_cost = 0.0
    total_confidence = 0.0
    arch_legs = 0
    for leg in legs_evaluations:
        for sol in leg.get("pareto_solutions", []):
            if hasattr(sol, 'archetype') and sol.archetype == archetype:
                total_w_survival += sol.w_survival
                total_w_cost += sol.w_expected_cost
                total_confidence += sol.confidence
                arch_legs += 1

    avg_confidence = round(total_confidence / arch_legs, 1) if arch_legs > 0 else 0.0

    reasoning_log = (
        f"Arquetipo '{archetype}': evaluados {arch_legs} tramos. "
        f"Costo total ponderado: {total_w_cost:.2f} ARS. "
        f"Riesgo acumulado (w_survival): {total_w_survival:.4f}. "
        f"Confianza promedio: {avg_confidence}%. "
        f"Phase2: {p2_time*1000:.0f}ms, Phase3: {p3_time*1000:.0f}ms."
    )

    # Per-assignment financial metrics
    for v_plan in plan:
        n_dests = len(v_plan.get("route_destinations", []))
        v_plan["financial_metrics"] = {
            "assigned_destinations": n_dests,
            "estimated_cost_share": round(total_w_cost / max(len(plan), 1), 2),
        }

    plan_dict = {

        "assignments": plan,

        "uncovered": uncovered,

        "segments_pareto": legs_evaluations,
        "metrics": {
            "phase2_time_ms": p2_time * 1000,
            "phase3_time_ms": p3_time * 1000,
            "start_time": t0_p2,
            "end_time": time.time()
        },
        "reasoning_log": reasoning_log,
        "plan_financial_summary": {
            "total_expected_cost": round(total_w_cost, 2),
            "total_w_survival": round(total_w_survival, 4),
            "avg_confidence": avg_confidence,
            "legs_evaluated": arch_legs
        },
        "topology_visuals": {
            "toll_markers": _detect_toll_crossings(nodes_of_interest, plan, base_graph, client_cost_env, departure_time),
            "risk_polygons": _get_h3_polygons(p2_subgraph_nodes, threat_matrix)
        }
    }

    # Fracture 5: Build detailed cost breakdown for each assignment
    for a_plan in plan:
        # We need the full path of nodes for distance/tolls
        # r_indices contains the RX indices of the route
        path_nodes = a_plan["route_indices"]
        a_plan["cost_breakdown"] = _calculate_cost_breakdown(
            path_nodes, 
            a_plan["schedule"], 
            base_graph, 
            client_cost_env,
            departure_time or f"{shift_start_minutes//60:02d}:{shift_start_minutes%60:02d}"
        )

    return archetype, plan_dict, legs_count, fallback_counter[0]

def _haversine_path_km(path_rx, base_graph) -> float:
    total_km = 0.0
    for i in range(len(path_rx) - 1):
        u_node = base_graph[path_rx[i]]
        v_node = base_graph[path_rx[i+1]]
        # Simple haversine-like distance
        phi1, lam1 = math.radians(u_node.lat), math.radians(u_node.lon)
        phi2, lam2 = math.radians(v_node.lat), math.radians(v_node.lon)
        dphi = phi2 - phi1
        dlam = lam2 - lam1
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        total_km += 6371.0 * c
    return total_km

def _detect_toll_crossings(nodes_of_interest, plan, base_graph, cost_env, departure_time) -> list:
    markers = []
    # Identify unique toll edge crossings in the final routes
    for a_plan in plan:
        path_rx = a_plan.get("route_indices", [])
        for i in range(len(path_rx) - 1):
            u_idx, v_idx = path_rx[i], path_rx[i+1]
            try:
                # get_edge_data returns the EdgePayload
                edge_payload = base_graph.get_edge_data(u_idx, v_idx)
                if not edge_payload: continue
                
                name_upper = edge_payload.name.upper() if getattr(edge_payload, 'name', None) else ""
                is_toll = False
                toll_name = ""
                
                if "25 DE MAYO" in name_upper:
                    is_toll, toll_name = True, "Peaje AUSA 25 de Mayo"
                elif "PERITO MORENO" in name_upper:
                    is_toll, toll_name = True, "Peaje AUSA Perito Moreno"
                elif "ILLIA" in name_upper:
                    is_toll, toll_name = True, "Peaje AUSA Illia"
                elif "ACCESO NORTE" in name_upper or "PANAMERICANA" in name_upper:
                    is_toll, toll_name = True, "Peaje Acceso Norte"
                elif "ACCESO OESTE" in name_upper:
                    is_toll, toll_name = True, "Peaje Acceso Oeste"
                
                if is_toll:
                    u_node = base_graph[u_idx]
                    markers.append({
                        "lat": u_node.lat,
                        "lon": u_node.lon,
                        "name": toll_name,
                        "vehicle_id": a_plan["vehicle"].id
                    })
            except:
                continue
    return markers

def _get_h3_polygons(node_set, threat_matrix) -> list:
    import h3
    polygons = []
    # Collect all unique H3 cells in the filtered subgraph
    seen_h3 = set()
    # In this context, we check the threat_matrix for high risk areas
    for h3_idx, mu in threat_matrix.items():
        if mu > 1.1: # High risk threshold
            # Get boundary coordinates for the H3 cell
            try:
                # h3.cell_to_boundary returns lat-lon tuples
                boundary = h3.cell_to_boundary(h3_idx)
                polygons.append({
                    "h3_index": h3_idx,
                    "intensity": mu,
                    "boundary": [[lat, lon] for lat, lon in boundary]
                })
            except:
                continue
    return polygons

def _calculate_cost_breakdown(path_nodes, schedule, base_graph, cost_env, start_time_str) -> dict:
    from src.api.schemas import CostBreakdown
    
    # Defaults de Ecuación de Colapso (Launch Plan 2.0)
    gasoil = getattr(cost_env, "precio_gasoil_ars", 1865.0)
    l_por_km = getattr(cost_env, "consumo_l_por_km", 0.33)
    dolar_mep = getattr(cost_env, "dolar_mep_ars", 1415.52)
    viatico = 15671.16

    dist_km = _haversine_path_km(path_nodes, base_graph)
    
    # OPEX Variable (CKM)
    comb = dist_km * l_por_km * gasoil
    neum = dist_km * 57.00
    mant = dist_km * 135.40
    
    # OPEX Fijo (CH)
    # Duración total desde el primer al último punto del schedule
    if schedule and len(schedule) >= 2:
        dur_min = (schedule[-1]["suggested_arrival_min"] or 0) - (schedule[0]["suggested_arrival_min"] or 0)
    else:
        dur_min = 0
    dur_hr = max(dur_min, 0) / 60.0
    
    lab = dur_hr * 12140.27
    amort = dur_hr * 4234.84
    seg = dur_hr * 1818.18
    tele = dur_hr * 937.50

    # Peajes
    peajes = _detect_toll_crossings(path_nodes, schedule, base_graph, cost_env, start_time_str)
    costo_peajes = sum(p.get("costo_ars", 0) for p in peajes)

    total = comb + neum + mant + lab + amort + seg + tele + costo_peajes + viatico
    
    return CostBreakdown(
        distancia_km=round(dist_km, 2),
        consumo_litros=round(dist_km * l_por_km, 2),
        costo_combustible_ars=round(comb, 2),
        costo_neumaticos_ars=round(neum, 2),
        costo_mantenimiento_ars=round(mant, 2),
        duracion_horas=round(dur_hr, 2),
        costo_laboral_hora=12140.27,
        costo_amort_hora=4234.84,
        costo_seguros_hora=1818.18,
        costo_telemetria_hora=937.50,
        costo_peajes_ars=round(costo_peajes, 2),
        costo_total_ars=round(total, 2),
        costo_total_usd=round(total / dolar_mep, 2)
    ).model_dump()





async def calculate_fleet(payload: FleetRequest, request: Any) -> FleetResponse:

    t0_total = time.time()

    base_graph = request.app.state.base_graph

    osm_to_rx = request.app.state.osm_to_rx

    rx_to_osm = request.app.state.rx_to_osm

    

    # Resolver departure_hour para trafico dinamico

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

    logger.info(f"VRP departure_hour resolved to {departure_hour}")

    

    # Selección de juez: standard vs premium (estocástico)

    judge = request.app.state.judge_premium if (

        payload.stochastic_mode and getattr(request.app.state, 'judge_premium', None) is not None

    ) else request.app.state.judge

    

    # --- PHASE 1 ---

    # "Filter app.state.base_graph by bounding box using the NodePayload (lat/lon) already in memory."

    logger.info("Phase 1: Bounding Box Filter directly from app.state.base_graph. DuckDB is NOT opened and read_parquet is NOT used.")

    

    t0_p1 = time.time()

    min_lat = min(v.origin_lat for v in payload.vehicles)

    max_lat = max(v.origin_lat for v in payload.vehicles)

    min_lon = min(v.origin_lon for v in payload.vehicles)

    max_lon = max(v.origin_lon for v in payload.vehicles)

    

    for d in payload.destinations:

        min_lat = min(min_lat, d.lat)

        max_lat = max(max_lat, d.lat)

        min_lon = min(min_lon, d.lon)

        max_lon = max(max_lon, d.lon)



    # 15% Padding

    pad_lat = (max_lat - min_lat) * 0.15

    pad_lon = (max_lon - min_lon) * 0.15

    

    # Fallback if there's only one point or zero var

    if pad_lat == 0: pad_lat = 0.05

    if pad_lon == 0: pad_lon = 0.05

    

    min_lat -= pad_lat

    max_lat += pad_lat

    min_lon -= pad_lon

    max_lon += pad_lon

    

    spatial_index = request.app.state.spatial_index

    spatial_rx_indices = request.app.state.spatial_rx_indices

    

    # Buscar nodos dentro del bounding box usando query_ball_point

    # radio en grados (~50km)

    center = [(min_lat + max_lat) / 2, (min_lon + max_lon) / 2]

    radius = max((max_lat - min_lat), (max_lon - min_lon))

    candidate_indices = spatial_index.query_ball_point(center, radius)

    

    allowed_nodes = set([spatial_rx_indices[i] for i in candidate_indices])

    

    # Also need logic to ensure origins and destinations are in allowed_nodes

    # Map vehicles & destinations to RX indices

    V_rx = []

    for v in payload.vehicles:

        osm_id = get_nearest_node_osm_id(v.origin_lat, v.origin_lon)

        rx_idx = get_rx_idx_for_osm(osm_to_rx, osm_id)

        if rx_idx is not None:

            V_rx.append(rx_idx)

            allowed_nodes.add(rx_idx)

        else:

            raise HTTPException(status_code=400, detail=f"Vehicle {v.id} origin node unreachable.")

    

    D_rx = []

    for d in payload.destinations:

        osm_id = get_nearest_node_osm_id(d.lat, d.lon)

        rx_idx = get_rx_idx_for_osm(osm_to_rx, osm_id)

        if rx_idx is not None:

            D_rx.append(rx_idx)

            allowed_nodes.add(rx_idx)

        else:

            raise HTTPException(status_code=400, detail=f"Destination {d.id} root node unreachable.")

            

    # Count restricted edges in this subgraph 

    # (Since graph obj has no direct count of induced subgraph without filtering, we just iterate or set it up)

    # Note: Rustworkx has subgraph() but for memory safety we just calculate connections.

    total_edges_subgraph = len(allowed_nodes)

    logger.info(f"Phase 1 complete in {(time.time() - t0_p1)*1000:.1f}ms. Total distinct nodes: {len(allowed_nodes)}, Nodos en subgrafo: {total_edges_subgraph}")

    

    # Target archetypes (Excluding unicorn from Phase 2/3)

    available_archetypes = [a for a in payload.allowed_archetypes if a != "unicornio"]

    if not available_archetypes:

        available_archetypes = ["equilibrista"]

    

    # Result dictionary by archetype

    archetype_plans = {}

    total_phase4_legs = 0

    total_fallback_edges = 0

    

    nodes_of_interest = V_rx + D_rx



    # Subgrafo acotado para Phase 2 — misma técnica que Phase 4

    # Radio basado en la diagonal total del conjunto de puntos

    all_lats = [base_graph[rx].lat for rx in nodes_of_interest]

    all_lons = [base_graph[rx].lon for rx in nodes_of_interest]

    p2_lat_center = (min(all_lats) + max(all_lats)) / 2

    p2_lon_center = (min(all_lons) + max(all_lons)) / 2

    p2_diagonal = math.sqrt(

        (max(all_lats) - min(all_lats))**2 +

        (max(all_lons) - min(all_lons))**2

    )

    # Radio generoso: 0.8x diagonal + mínimo 0.15 grados (~15km)

    # para garantizar rutas que rodean obstáculos urbanos

    p2_radius = max(p2_diagonal * 0.8, 0.15)



    p2_candidates = spatial_index.query_ball_point(

        [p2_lat_center, p2_lon_center], p2_radius

    )

    p2_subgraph_nodes = set(spatial_rx_indices[i] for i in p2_candidates)

    # Garantizar que todos los nodos de interés estén incluidos

    p2_subgraph_nodes.update(nodes_of_interest)

    logger.info(f"Phase 2 subgraph: {len(p2_subgraph_nodes):,} nodos (vs 185,112 total)")



    client_cost_env = request.app.state.cost_settings

    if payload.economic_profile:

        override_dict = payload.economic_profile.model_dump(exclude_unset=True)

        base_dict = client_cost_env.__dict__.copy()

        base_dict.update(override_dict)

        from src.config.settings import CostSettings

        client_cost_env = CostSettings(**base_dict)



    from src.block5.cost_matrix_builder import build_time_matrix_only

    shared_time_matrix = build_time_matrix_only(

        base_graph, nodes_of_interest,

        client_cost_env, osm_to_rx, departure_hour, speed_profiles,

        node_filter=p2_subgraph_nodes

    )



    # Construir ventanas horarias una sola vez también

    vehicle_windows = [(0, 1440)] * len(V_rx)

    dest_windows = [(int(d.tw_start_min), int(d.tw_end_min)) for d in payload.destinations]

    time_windows = vehicle_windows + dest_windows

    has_real_windows = any(tw != (0, 1440) for tw in dest_windows)



        # Service times: 0 para vehículos (depósitos), service_time_min para destinos
    vehicle_service_times = [0] * len(V_rx)
    dest_service_times = [int(d.service_time_min) for d in payload.destinations]
    service_times = vehicle_service_times + dest_service_times

    max_shift_per_vehicle = [v.max_shift_minutes for v in payload.vehicles]

    # Paralelizar arquetipos en thread pool
    # OR-Tools y rustworkx liberan el GIL — ThreadPoolExecutor es suficiente
    loop = asyncio.get_event_loop()
    
    archetype_futures = [
        loop.run_in_executor(
            _archetype_executor,
            _compute_archetype_plan,
            archetype,
            base_graph,
            nodes_of_interest,
            client_cost_env,
            request.app.state.threat_matrix,
            judge,
            osm_to_rx,
            rx_to_osm,
            shared_time_matrix,
            time_windows,
            has_real_windows,
            service_times,
            max_shift_per_vehicle,
            payload,
            spatial_index,
            spatial_rx_indices,
            departure_hour,
            speed_profiles,
            p2_subgraph_nodes,
            payload.shift_start_minutes,
            payload.departure_time
        )
        for archetype in available_archetypes
    ]
    
    archetype_results = await asyncio.gather(*archetype_futures)
    
    for archetype, plan_dict, legs_count, fallback_count in archetype_results:
        archetype_plans[archetype] = plan_dict
        total_phase4_legs += legs_count
        total_fallback_edges += fallback_count
        
    shift_limit_enforced = any(v.max_shift_minutes < 1440 for v in payload.vehicles)

    total_time_ms = (time.time() - t0_total) * 1000
    
    has_real_windows = any(
        getattr(d, "tw_start_min", 0) != 0 or getattr(d, "tw_end_min", 1440) != 1440 
        for d in payload.destinations
    )
    return FleetResponse(
        subgraph_edges=total_edges_subgraph,
        total_time_ms=total_time_ms,
        phase4_total_legs=total_phase4_legs,
        toll_fallback_edges=total_fallback_edges,
        plans=archetype_plans,
        time_windows_enforced=has_real_windows,
        shift_limit_enforced=shift_limit_enforced
    )

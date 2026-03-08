# src/block5/vrp_orchestrator.py
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Any
from fastapi import HTTPException
import math

from src.api.schemas import FleetRequest, FleetResponse, ParetoResult
from src.block5.cost_matrix_builder import build_dense_cost_matrix
from src.block5.vrp_solver import solve_vrp
from src.bloque1.duckdb_ingestor import get_nearest_node_osm_id
from src.bloque4.rx_adapter import get_rx_idx_for_osm, build_legacy_graph
from src.bloque4.multiobjective_engine import MultiObjectiveEngine
from src.bloque4.pareto import ParetoFrontResult

logger = logging.getLogger("VRP_Orchestrator")

async def calculate_fleet(payload: FleetRequest, request: Any) -> FleetResponse:
    semaphore = request.app.state.fleet_semaphore
    
    if semaphore.locked():
        raise HTTPException(status_code=429, detail="Server overloaded. At capacity of 1 concurrent fleet requests.")
        
    async with semaphore:
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
        
        allowed_nodes = set()
        for rx_idx in rx_to_osm.keys():
            node_payload = base_graph.get_node_data(rx_idx)
            if hasattr(node_payload, 'lat') and hasattr(node_payload, 'lon'):
                if min_lat <= node_payload.lat <= max_lat and min_lon <= node_payload.lon <= max_lon:
                    allowed_nodes.add(rx_idx)
        
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
        
        for archetype in available_archetypes:
            # --- PHASE 2 ---
            t0_p2 = time.time()
            nodes_of_interest = V_rx + D_rx
            
            client_cost_env = request.app.state.cost_settings
            if payload.economic_profile:
                override_dict = payload.economic_profile.model_dump(exclude_unset=True)
                base_dict = client_cost_env.__dict__.copy()
                base_dict.update(override_dict)
                from src.config.settings import CostSettings
                client_cost_env = CostSettings(**base_dict)
                
            cost_matrix = build_dense_cost_matrix(
                base_graph, nodes_of_interest, archetype,
                client_cost_env, request.app.state.threat_matrix,
                request.app.state.judge, osm_to_rx,
                departure_hour=departure_hour,
                speed_profiles=speed_profiles
            )
            p2_time = time.time() - t0_p2
            logger.info(f"Phase 2 complete for {archetype} in {p2_time*1000:.1f}ms")
            
            # --- PHASE 3 ---
            t0_p3 = time.time()
            capacities = [v.capacity_tons for v in payload.vehicles]
            demands = [0.0] * len(V_rx) + [d.demand_tons for d in payload.destinations]
            
            routes = solve_vrp(
                cost_matrix=cost_matrix,
                vehicle_capacities=capacities,
                demands=demands,
                num_vehicles=len(V_rx),
                time_limit_seconds=payload.time_limit_seconds
            )
            p3_time = time.time() - t0_p3
            logger.info(f"Phase 3 complete for {archetype} in {p3_time*1000:.1f}ms")
            
            if not routes:
                archetype_plans[archetype] = {"error": "No viable fleet assignment found."}
                continue
            
            # Extract assigned destinations by route mapping the returned matrix indices (0..V-1 = Vehicles, V..N = Destinations)
            plan = []
            assigned_dest_indices = set()
            for v_idx, route in enumerate(routes):
                v_destinations = []
                for node_idx in route:
                    if node_idx >= len(V_rx):  # It's a destination
                        d_idx = node_idx - len(V_rx)
                        v_destinations.append(payload.destinations[d_idx])
                        assigned_dest_indices.add(d_idx)
                plan.append({
                    "vehicle": payload.vehicles[v_idx],
                    "route_destinations": v_destinations,
                    "route_indices": route
                })
            
            uncovered = [payload.destinations[i] for i in range(len(payload.destinations)) if i not in assigned_dest_indices]
            
            # --- PHASE 4 ---
            # Run the original Pareto Engine only on the K actual allocated segments.
            # The Unicorn is evaluated here, segment by segment.
            legs_evaluations = []
            judge = request.app.state.judge
            client_cost_env = request.app.state.cost_settings
            
            for v_plan in plan:
                v_obj = v_plan["vehicle"]
                r_indices = v_plan["route_indices"]
                
                for step in range(len(r_indices) - 1):
                    source_idx = r_indices[step]
                    target_idx = r_indices[step + 1]
                    
                    if source_idx == target_idx:
                        continue
                        
                    s_rx = nodes_of_interest[source_idx]
                    t_rx = nodes_of_interest[target_idx]
                    
                    # Prepare Legacy Proxy Zero-Copy
                    legacy_graph, config, _ = build_legacy_graph(
                        rx_graph=base_graph,
                        rx_to_osm=rx_to_osm,
                        judge=judge,
                        source_rx_idx=s_rx,
                        target_rx_idx=t_rx,
                        cost_env=client_cost_env,
                        allowed_nodes=allowed_nodes,
                        departure_hour=departure_hour,
                        speed_profiles=speed_profiles
                    )
                    
                    node_coords = {n.node_id: (n.lat, n.lon) for n in legacy_graph.nodes if n.lat != 0.0 or n.lon != 0.0}
                    engine = MultiObjectiveEngine(eps_1=0.1, eps_2=50.0, max_total_labels=150000)
                    frontier_labels = engine.solve(legacy_graph, str(s_rx), str(t_rx), node_coords=node_coords)
                    
                    if frontier_labels:
                        pareto_result = ParetoFrontResult.from_labels(frontier_labels, engine)
                        archetipos = {
                            "tanque": pareto_result.extract_tank(),
                            "apostador": pareto_result.extract_gambler(),
                            "equilibrista": pareto_result.extract_tightrope(),
                            "unicornio": pareto_result.extract_unicorn(),
                        }
                        
                        leg_sols = []
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

                        for arch_name, sol in archetipos.items():
                            if sol:
                                conf = normalize_confidence(sol.w_survival)
                                leg_sols.append(ParetoResult(
                                    archetype=arch_name,
                                    w_survival=sol.w_survival,
                                    w_expected_cost=sol.w_expected_cost,
                                    route_nodes=list(sol.path),
                                    confidence=conf
                                ))
                        
                        legs_evaluations.append({
                            "source_osm": rx_to_osm[s_rx],
                            "target_osm": rx_to_osm[t_rx],
                            "pareto_solutions": leg_sols
                        })
                        total_phase4_legs += 1
            
            archetype_plans[archetype] = {
                "assignments": plan,
                "uncovered": uncovered,
                "segments_pareto": legs_evaluations,
                "metrics": {
                    "phase2_time_ms": p2_time * 1000,
                    "phase3_time_ms": p3_time * 1000
                }
            }
            
        total_time_ms = (time.time() - t0_total) * 1000
        
        return FleetResponse(
            subgraph_edges=total_edges_subgraph,
            total_time_ms=total_time_ms,
            phase4_total_legs=total_phase4_legs,
            plans=archetype_plans
        )

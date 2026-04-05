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
from src.bloque4.rx_adapter import get_rx_idx_for_osm, build_legacy_graph
from src.bloque4.multiobjective_engine import MultiObjectiveEngine
from src.bloque4.pareto import ParetoFrontResult

logger = logging.getLogger("VRP_Orchestrator")

_archetype_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="archetype")

def _coord_distance_km(coords: list) -> float:
    if not coords or len(coords) < 2:
        return 0.0
    total = 0.0
    for i in range(len(coords) - 1):
        lat1, lon1 = coords[i]
        lat2, lon2 = coords[i+1]
        phi1, lam1 = math.radians(lat1), math.radians(lon1)
        phi2, lam2 = math.radians(lat2), math.radians(lon2)
        dphi = phi2 - phi1
        dlam = lam2 - lam1
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        total += 6371.0 * c
    return total

def _haversine_path_km(path_rx, base_graph) -> float:
    total_km = 0.0
    for i in range(len(path_rx) - 1):
        u_node = base_graph[path_rx[i]]
        v_node = base_graph[path_rx[i+1]]
        phi1, lam1 = math.radians(u_node.lat), math.radians(u_node.lon)
        phi2, lam2 = math.radians(v_node.lat), math.radians(v_node.lon)
        dphi = phi2 - phi1
        dlam = lam2 - lam1
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        total_km += 6371.0 * c
    return total_km

def _detect_toll_crossings(path_nodes, plan_ref, base_graph, cost_env, departure_time) -> list:
    markers = []
    for i in range(len(path_nodes) - 1):
        u_idx, v_idx = path_nodes[i], path_nodes[i+1]
        try:
            edge_payload = base_graph.get_edge_data(u_idx, v_idx)
            if not edge_payload: continue
            
            name_upper = edge_payload.name.upper() if getattr(edge_payload, 'name', None) else ""
            is_toll = False
            toll_name = ""
            cost = 0.0
            
            if "25 DE MAYO" in name_upper:
                is_toll, toll_name, cost = True, "Peaje AUSA 25 de Mayo", getattr(cost_env, "ausa_25_mayo_ars", 1200.0)
            elif "PERITO MORENO" in name_upper:
                is_toll, toll_name, cost = True, "Peaje AUSA Perito Moreno", getattr(cost_env, "ausa_25_mayo_ars", 1200.0)
            elif "ILLIA" in name_upper:
                is_toll, toll_name, cost = True, "Peaje AUSA Illia", getattr(cost_env, "ausa_paseo_bajo_ars", 900.0)
            elif "ACCESO NORTE" in name_upper or "PANAMERICANA" in name_upper:
                is_toll, toll_name, cost = True, "Peaje Acceso Norte", getattr(cost_env, "acceso_norte_oeste_ars", 1300.0)
            elif "ACCESO OESTE" in name_upper:
                is_toll, toll_name, cost = True, "Peaje Acceso Oeste", getattr(cost_env, "acceso_norte_oeste_ars", 1300.0)
            
            if is_toll:
                u_node = base_graph[u_idx]
                markers.append({
                    "lat": u_node.lat,
                    "lon": u_node.lon,
                    "name": toll_name,
                    "costo_ars": cost,
                    "vehicle_id": getattr(plan_ref, 'id', 'audit') if plan_ref else 'audit'
                })
        except:
            continue
    return markers

def _get_h3_polygons(node_set, threat_matrix) -> list:
    import h3
    polygons = []
    for h3_idx, mu in threat_matrix.items():
        if mu > 1.1:
            try:
                boundary = h3.cell_to_boundary(h3_idx)
                polygons.append({
                    "h3_index": h3_idx,
                    "intensity": mu,
                    "boundary": [[float(lat), float(lon)] for lat, lon in boundary]
                })
            except:
                continue
    return polygons

def _calculate_cost_breakdown(path_nodes, schedule, base_graph, cost_env, start_time_str, real_dist_km: float = None, destinations_payload: list = None) -> dict:
    from src.api.schemas import CostBreakdown
    
    # ─── Extraer Perfiles CFO (Seguro y anidado) ───
    opex = cost_env.opex_movil
    personal = cost_env.personal
    capex = cost_env.capex
    dolar_mep = getattr(cost_env, 'dolar_mep_ars', 1420.0)

    dist_km = real_dist_km if real_dist_km is not None else _haversine_path_km(path_nodes, base_graph)
    
    if schedule and len(schedule) >= 2:
        dur_min = (schedule[-1]["suggested_arrival_min"] or 0) - (schedule[0]["suggested_arrival_min"] or 0)
    else:
        dur_min = 0
    dur_hr = max(dur_min, 0) / 60.0

    # ─── TAREA 5: Cálculo de Tiempos Muertos (Wait Time) ───
    wait_min = 0
    if schedule and destinations_payload:
        dest_lookup = {d.id: d for d in destinations_payload}
        for stop in schedule:
            d_id = stop.get("destination_id")
            if d_id and d_id in dest_lookup:
                d_meta = dest_lookup[d_id]
                arrival = stop.get("suggested_arrival_min")
                tw_start = getattr(d_meta, "tw_start_min", 0)
                if arrival is not None and arrival < tw_start:
                    wait_min += (tw_start - arrival)
    wait_hr = wait_min / 60.0
    
    # ─── 1. OPEX Móvil (Target: Costo/KM) ───
    comb = dist_km * opex.consumo_l_km * opex.gasoil_ars_l
    neum = dist_km * opex.neumaticos_km_ars
    mant = dist_km * opex.mantenimiento_km_ars
    opex_dist_total = comb + neum + mant
    ckm_calculado = opex_dist_total / dist_km if dist_km > 0 else 0.0

    # ─── 2. Personal & CH (Target: Costo/Hora - Parte Laboral) ───
    costo_laboral_mensual = (personal.sueldo_basico_ars * personal.cargas_sociales_factor) + \
                            personal.bono_mensual_ars + \
                            (personal.viatico_dia_ars * 22) + \
                            personal.provision_sac_vacaciones_ars
    
    ch_laboral = costo_laboral_mensual / personal.jornada_mensual_hs
    opex_time_total = (dur_hr + wait_hr) * ch_laboral # El tiempo de espera penaliza el margen

    # ─── 3. CAPEX & CH (Target: Costo/Hora - Parte Estructural) ───
    amort_mensual = (capex.valor_unidad_ars * (1 - capex.valor_recupero_pct)) / capex.vida_util_meses
    ch_estructural = (amort_mensual + capex.seguros_patentes_mes_ars + capex.telemetria_mes_ars) / personal.jornada_mensual_hs
    capex_amort_total = dur_hr * ch_estructural

    # ─── 4. Fijos, Peajes, Custodia y Riesgo ───
    peajes = _detect_toll_crossings(path_nodes, None, base_graph, cost_env, start_time_str)
    costo_peajes = sum(p.get("costo_ars", 0) for p in peajes)
    viatico_total = personal.viatico_dia_ars
    
    # Custodia y Riesgo (Nuevas variables CFO)
    vel_kmh = getattr(cost_env, 'velocidad_comercial_kmh', 40.0)
    custodia_hr = getattr(cost_env, 'custodia_hora_ars', 0.0)
    franquicia_usd = getattr(cost_env, 'franquicia_seguro_usd', 1500.0)
    
    total_custodia = dur_hr * custodia_hr # Simplificado para el reporte
    # El riesgo se calcula como exposición probabilística (1% fallback de siniestralidad por ruta)
    total_riesgo_exposicion = 0.01 * (franquicia_usd * dolar_mep) 

    fixed_costs_total = costo_peajes + viatico_total
    total_viaje_ars = opex_dist_total + opex_time_total + capex_amort_total + fixed_costs_total + total_custodia + total_riesgo_exposicion

    reasons = []
    if wait_hr > 0.5:
        reasons.append(f"Inactividad operativa: {wait_hr:.1f} hrs de espera por ventanas horarias.")
    if dur_hr > 0 and (dist_km / dur_hr) < (vel_kmh * 0.6):
        reasons.append(f"Alerta: Baja velocidad comercial detectada ({dist_km/dur_hr:.1f} km/h - Target: {vel_kmh}).")
    if costo_peajes > 4000:
        reasons.append("Detalle: Impacto considerable de peajes en ruta auditada.")

    return CostBreakdown(
        distancia_km=round(dist_km, 2),
        consumo_litros=round(dist_km * opex.consumo_l_km, 2),
        precio_gasoil_ars=round(opex.gasoil_ars_l, 2),
        consumo_l_por_km=round(opex.consumo_l_km, 3),
        costo_combustible_ars=round(comb, 2),
        costo_neumaticos_ars=round(neum, 2),
        costo_mantenimiento_ars=round(mant, 2),
        ckm_total_ars=round(ckm_calculado, 2),
        duracion_horas=round(dur_hr, 2),
        costo_laboral_hora=round(ch_laboral, 2),
        costo_amort_hora=round(amort_mensual / personal.jornada_mensual_hs, 2),
        costo_seguros_hora=round(capex.seguros_patentes_mes_ars / personal.jornada_mensual_hs, 2),
        costo_telemetria_hora=round(capex.telemetria_mes_ars / personal.jornada_mensual_hs, 2),
        ch_total_ars=round(ch_laboral + ch_estructural, 2),
        peajes_cruzados=peajes,
        costo_peajes_ars=round(costo_peajes, 2),
        viatico_ars=round(viatico_total, 2),
        opex_distance_ars=round(opex_dist_total, 2),
        opex_time_ars=round(opex_time_total, 2),
        capex_amortization_ars=round(capex_amort_total, 2),
        fixed_costs_ars=round(fixed_costs_total, 2),
        custodia_ars=round(total_custodia, 2),
        exposure_risk_ars=round(total_riesgo_exposicion, 2),
        executive_variance_analysis=reasons,
        costo_total_ars=round(total_viaje_ars, 2),
        costo_total_usd=round(total_viaje_ars / dolar_mep, 2),
        dolar_mep=dolar_mep,
        fuente_precios="CFO-Grade / Mar 2026 Audit"
    ).model_dump()


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
    
    fallback_counter = [0]
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

    t0_p3 = time.time()
    num_vehicles = sum(1 for _ in payload.vehicles)
    capacities = [v.capacity_tons for v in payload.vehicles]
    demands = [0.0] * num_vehicles + [d.demand_tons for d in payload.destinations]

    # Prioridad 0: Extraer horarios de salida reales para el VRP
    v_start_times = []
    for v_input in payload.vehicles:
        v_shift_start = shift_start_minutes
        if v_input.departure_time:
            try:
                h, m = map(int, v_input.departure_time.split(":"))
                v_shift_start = h * 60 + m
            except: pass
        v_start_times.append(v_shift_start)

    result = solve_vrp(
        cost_matrix=cost_matrix,
        vehicle_capacities=capacities,
        demands=demands,
        num_vehicles=num_vehicles,
        time_limit_seconds=payload.time_limit_seconds,
        time_matrix=shared_time_matrix,
        time_windows=time_windows if has_real_windows else None,
        service_times=service_times,
        max_shift_minutes_per_vehicle=max_shift_per_vehicle,
        vehicle_start_times=v_start_times
    )
    p3_time = time.time() - t0_p3

    if not result:
        return archetype, {"error": "No viable fleet assignment found."}, 0, 0

    routes, schedules = result
    V_rx_count = num_vehicles
    plan = []
    assigned_dest_indices = set()
    
    for v_idx, (route, schedule) in enumerate(zip(routes, schedules)):
        v_input = payload.vehicles[v_idx]
        
        # Override Excel -> Global Fallback
        v_shift_start = shift_start_minutes
        if v_input.departure_time:
            try:
                h, m = map(int, v_input.departure_time.split(":"))
                v_shift_start = h * 60 + m
            except: pass

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
                    abs_min = schedule[step_idx]["suggested_arrival_min"]
                    v_schedule.append({
                        "destination_id": dest.id,
                        "suggested_arrival_min": abs_min,
                        "earliest_arrival_min": schedule[step_idx]["earliest_arrival_min"],
                        "latest_arrival_min": schedule[step_idx]["latest_arrival_min"],
                        "suggested_arrival_hhmm": f"{abs_min // 60:02d}:{abs_min % 60:02d}" if abs_min is not None else None
                    })
                    if abs_min is not None:
                        last_arrival_min = abs_min

        if v_destinations and len(route) >= 2:
            last_node_idx = route[-2] if route[-1] < V_rx_count else route[-1]
            depot_idx = v_idx
            if last_node_idx < len(shared_time_matrix) and depot_idx < len(shared_time_matrix[last_node_idx]):
                return_travel = shared_time_matrix[last_node_idx][depot_idx]
                if return_travel is not None and return_travel < 99999:
                    last_dest_service = int(v_destinations[-1].service_time_min) if v_destinations else 0
                    abs_return = last_arrival_min + last_dest_service + int(return_travel)
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

    legs_evaluations = []
    legs_count = 0
    leg_real_distances = {}
    leg_coords = {}

    for v_plan in plan:
        r_indices = v_plan["route_indices"]
        for step in range(len(r_indices) - 1):
            source_idx = r_indices[step]
            target_idx = r_indices[step + 1]
            if source_idx == target_idx: continue
            
            leg_key = (source_idx, target_idx)
            if leg_key in leg_real_distances: continue

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
                    normalize_confidence = lambda w, wm=w_min, wmx=w_max: round(100.0 * (wmx - w) / (wmx - wm), 1) if wmx != wm else 100.0
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
                        
                        if arch_name == archetype:
                            leg_real_distances[leg_key] = _coord_distance_km(coords)
                            leg_coords[leg_key] = coords

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

    for a_plan in plan:
        r_indices = a_plan["route_indices"]
        real_dist_total = 0.0
        full_route_coords = []
        for step in range(len(r_indices) - 1):
            source_idx = r_indices[step]
            target_idx = r_indices[step + 1]
            real_dist_total += leg_real_distances.get((source_idx, target_idx), 0.0)
            leg_c = leg_coords.get((source_idx, target_idx), [])
            if leg_c:
                if not full_route_coords:
                    full_route_coords.extend(leg_c)
                else:
                    full_route_coords.extend(leg_c[1:])
        
        a_plan["route_coordinates"] = full_route_coords

    for a_plan in plan:
        path_nodes = a_plan["route_indices"]
        real_dist_total = 0.0
        for step in range(len(path_nodes) - 1):
            source_idx = path_nodes[step]
            target_idx = path_nodes[step + 1]
            real_dist_total += leg_real_distances.get((source_idx, target_idx), 0.0)

        # Usar el horario de salida del camión para la hoja de ruta
        v_input = a_plan["vehicle"]
        v_shift_start = shift_start_minutes
        if v_input.departure_time:
            try:
                h, m = map(int, v_input.departure_time.split(":"))
                v_shift_start = h * 60 + m
            except: pass
        v_start_hhmm = f"{v_shift_start//60:02d}:{v_shift_start%60:02d}"

        a_plan["cost_breakdown"] = _calculate_cost_breakdown(
            path_nodes,
            a_plan["schedule"],
            base_graph,
            client_cost_env,
            v_start_hhmm,
            real_dist_km=real_dist_total,
            destinations_payload=payload.destinations
        )

    agg_opex_dist = sum(v.get("cost_breakdown", {}).get("opex_distance_ars", 0) for v in plan)
    agg_opex_time = sum(v.get("cost_breakdown", {}).get("opex_time_ars", 0) for v in plan)
    agg_capex = sum(v.get("cost_breakdown", {}).get("capex_amortization_ars", 0) for v in plan)
    agg_fixed = sum(v.get("cost_breakdown", {}).get("fixed_costs_ars", 0) for v in plan)
    agg_custodia = sum(v.get("cost_breakdown", {}).get("custodia_ars", 0) for v in plan)
    agg_exposure_risk = sum(v.get("cost_breakdown", {}).get("exposure_risk_ars", 0) for v in plan)
    agg_total = agg_opex_dist + agg_opex_time + agg_capex + agg_fixed + agg_custodia + agg_exposure_risk
    agg_variance = []
    for v in plan:
        agg_variance.extend(v.get("cost_breakdown", {}).get("executive_variance_analysis", []))
    agg_variance = list(set(agg_variance))[:5] 

    dolar_mep = getattr(client_cost_env, "dolar_mep_ars", 1415.52)

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
        "reasoning_log": (
            f"Arquetipo '{archetype}': {arch_legs} tramos reales evaluados. "
            f"OPEX Distancia auditado: $ {agg_opex_dist:.2f} ARS. "
            f"Phase2: {p2_time*1000:.0f}ms, Phase3: {p3_time*1000:.0f}ms."
        ),
        "plan_financial_summary": {
            "total_expected_cost": round(agg_total, 2),
            "total_w_survival": round(total_w_survival, 4),
            "avg_confidence": avg_confidence,
            "legs_evaluated": arch_legs,
            "opex_distance_ars": round(agg_opex_dist, 2),
            "opex_time_ars": round(agg_opex_time, 2),
            "capex_amortization_ars": round(agg_capex, 2),
            "fixed_costs_ars": round(agg_fixed, 2),
            "custodia_ars": round(agg_custodia, 2),
            "exposure_risk_ars": round(agg_exposure_risk, 2),
            "executive_variance_analysis": agg_variance,
            "costo_total_ars": round(agg_total, 2),
            "distancia_km": sum(v.get("cost_breakdown", {}).get("distancia_km", 0) for v in plan),
            "costo_total_usd": round(agg_total / dolar_mep, 2)
        },
        "topology_visuals": {
            "toll_markers": _detect_toll_crossings(nodes_of_interest, plan, base_graph, client_cost_env, departure_time),
            "risk_polygons": _get_h3_polygons(p2_subgraph_nodes, threat_matrix)
        }
    }

    return archetype, plan_dict, legs_count, fallback_counter[0]


async def calculate_fleet(payload: FleetRequest, request: Any) -> FleetResponse:
    t0_total = time.time()
    base_graph = request.app.state.base_graph
    osm_to_rx = request.app.state.osm_to_rx
    rx_to_osm = request.app.state.rx_to_osm

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

    risk_report_raw = None
    num_mc_scenarios = 0
    convergence_reached = False
    
    if payload.stochastic_mode:
        from src.bloque2.stochastic_adapter import StochasticBayesAdapter
        from src.bloque2.generator import MonteCarloGenerator, MonteCarloEngine
        from src.bloque2.incidents import ManifestLoader
        
        judge = request.app.state.judge.spawn_ephemeral_clone()
        
        try:
            base_net = request.app.state.mc_network_snapshot
            manifest = ManifestLoader.from_yaml("data/incident_manifest.yaml")
            
            generator = MonteCarloGenerator(base_net, manifest, seed=42)
            engine = MonteCarloEngine(generator)
            scenarios = engine.run(max_iter=500, window=50, e_limit=0.001)
            
            num_mc_scenarios = len(scenarios)
            convergence_reached = num_mc_scenarios < 500
            
            adapter = StochasticBayesAdapter.from_graph(base_graph)
            adapter.ingest(scenarios)
            overrides_df = adapter.to_overrides_df()
            
            judge.load_stochastic_overrides(overrides_df, request.app.state.osm_to_rx)
            risk_report_raw = judge.reliability_report()
            logger.info("Dynamic Stochastic Engine execution complete.")
        except Exception as e:
            logger.error(f"Failed to execute dynamic stochastic engine: {e}")
            judge = request.app.state.judge
    else:
        judge = request.app.state.judge

    logger.info("Phase 1: Bounding Box Filter directly from app.state.base_graph...")
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

    pad_lat = (max_lat - min_lat) * 0.10
    pad_lon = (max_lon - min_lon) * 0.10
    if pad_lat == 0: pad_lat = 0.05
    if pad_lon == 0: pad_lon = 0.05
    min_lat -= pad_lat
    max_lat += pad_lat
    min_lon -= pad_lon
    max_lon += pad_lon

    spatial_index = request.app.state.spatial_index
    spatial_rx_indices = request.app.state.spatial_rx_indices
    center = [(min_lat + max_lat) / 2, (min_lon + max_lon) / 2]
    radius = max((max_lat - min_lat), (max_lon - min_lon))
    candidate_indices = spatial_index.query_ball_point(center, radius)
    allowed_nodes = set([spatial_rx_indices[i] for i in candidate_indices])

    V_rx = []
    for v in payload.vehicles:
        candidates = spatial_index.query_ball_point([v.origin_lat, v.origin_lon], 0.01)
        if not candidates:
            candidates = spatial_index.query_ball_point([v.origin_lat, v.origin_lon], 0.05)
        if not candidates:
            raise HTTPException(status_code=400, detail=f"Vehicle {v.id} origin node unreachable.")
        # Encontrar el más cercano entre los candidatos
        best = min(candidates, key=lambda i: (spatial_rx_indices[i] and 
            (base_graph[spatial_rx_indices[i]].lat - v.origin_lat)**2 + 
            (base_graph[spatial_rx_indices[i]].lon - v.origin_lon)**2))
        rx_idx = spatial_rx_indices[best]
        V_rx.append(rx_idx)
        allowed_nodes.add(rx_idx)

    D_rx = []
    for d in payload.destinations:
        candidates = spatial_index.query_ball_point([d.lat, d.lon], 0.01)
        if not candidates:
            candidates = spatial_index.query_ball_point([d.lat, d.lon], 0.05)
        if not candidates:
            raise HTTPException(status_code=400, detail=f"Destination {d.id} root node unreachable.")
        best = min(candidates, key=lambda i: (
            (base_graph[spatial_rx_indices[i]].lat - d.lat)**2 + 
            (base_graph[spatial_rx_indices[i]].lon - d.lon)**2))
        rx_idx = spatial_rx_indices[best]
        D_rx.append(rx_idx)
        allowed_nodes.add(rx_idx)

    logger.info(f"Phase 1 complete: {len(V_rx)} vehicles + {len(D_rx)} destinations resolved in {(time.time()-t0_p1)*1000:.0f}ms")

    total_edges_subgraph = len(allowed_nodes)
    
    available_archetypes = [a for a in payload.allowed_archetypes if a != "unicornio"]
    if not available_archetypes:
        available_archetypes = ["equilibrista"]

    archetype_plans = {}
    total_phase4_legs = 0
    total_fallback_edges = 0
    nodes_of_interest = V_rx + D_rx

    all_lats = [base_graph[rx].lat for rx in nodes_of_interest]
    all_lons = [base_graph[rx].lon for rx in nodes_of_interest]
    p2_lat_center = (min(all_lats) + max(all_lats)) / 2
    p2_lon_center = (min(all_lons) + max(all_lons)) / 2
    p2_diagonal = math.sqrt((max(all_lats) - min(all_lats))**2 + (max(all_lons) - min(all_lons))**2)
    p2_radius = max(p2_diagonal * 0.5, 0.10)
    p2_candidates = spatial_index.query_ball_point([p2_lat_center, p2_lon_center], p2_radius)
    p2_subgraph_nodes = set(spatial_rx_indices[i] for i in p2_candidates)
    p2_subgraph_nodes.update(nodes_of_interest)
    logger.info(f"Phase 2 subgraph: {len(p2_subgraph_nodes):,} nodos (vs {len(base_graph):,} total)")

    # ─── INYECCIÓN CFO DIRECTA ───
    if payload.economic_profile:
        client_cost_env = payload.economic_profile
    else:
        from src.api.schemas import EconomicProfile
        client_cost_env = EconomicProfile()
    

    from src.block5.cost_matrix_builder import build_time_matrix_only
    shared_time_matrix = build_time_matrix_only(
        base_graph, nodes_of_interest,
        client_cost_env, osm_to_rx, departure_hour, speed_profiles,
        node_filter=p2_subgraph_nodes
    )

    vehicle_windows = [(0, 1440)] * len(V_rx)
    dest_windows = [(int(d.tw_start_min), int(d.tw_end_min)) for d in payload.destinations]
    time_windows = vehicle_windows + dest_windows
    has_real_windows = any(tw != (0, 1440) for tw in dest_windows)

    vehicle_service_times = [0] * len(V_rx)
    dest_service_times = [int(d.service_time_min) for d in payload.destinations]
    service_times = vehicle_service_times + dest_service_times
    max_shift_per_vehicle = [v.max_shift_minutes for v in payload.vehicles]

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
    network_risk_model = None
    if risk_report_raw:
        from src.api.schemas import EdgeRiskReport, NetworkRiskReport
        RISK_THRESHOLD = 0.05
        
        edge_reports = [
            EdgeRiskReport(
                edge_key=str(k), 
                prob_failure=v["prob_failure"], 
                impact_mean=v["impact_mean"]
            )
            for k, v in risk_report_raw.get("edges", {}).items()
            if v["prob_failure"] > RISK_THRESHOLD
        ]
        
        network_risk_model = NetworkRiskReport(
            system_prob_failure=risk_report_raw.get("system", {}).get("prob_failure", 0.0),
            system_impact_mean=risk_report_raw.get("system", {}).get("impact_mean", 0.0),
            total_edges_evaluated=len(risk_report_raw.get("edges", {})),
            monte_carlo_iterations=num_mc_scenarios,
            convergence_reached=convergence_reached,
            edges=edge_reports,
        )

    return FleetResponse(
        subgraph_edges=total_edges_subgraph,
        total_time_ms=total_time_ms,
        phase4_total_legs=total_phase4_legs,
        toll_fallback_edges=total_fallback_edges,
        plans=archetype_plans,
        time_windows_enforced=has_real_windows,
        shift_limit_enforced=shift_limit_enforced,
        network_risk=network_risk_model
    )
# src/block5/vrp_solver.py
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from typing import List, Optional, Tuple, Dict
import logging
import numpy as np
from src.block5.cost_matrix_builder import UNREACHABLE_PENALTY

logger = logging.getLogger("VRP_Solver")

def solve_vrp(
    cost_matrix: List[List[int]],
    vehicle_capacities: List[float],
    demands: List[float],
    num_vehicles: int,
    time_limit_seconds: int = 10,
    time_matrix: Optional[List[List[int]]] = None,
    time_windows: Optional[List[Tuple[int, int]]] = None,
    service_times: Optional[List[int]] = None,
    max_shift_minutes_per_vehicle: Optional[List[int]] = None,
    vehicle_start_times: Optional[List[int]] = None
) -> Optional[Tuple[List[List[int]], List[List[Dict]]]]:
    """
    Retorna (routes, schedules).
    routes: lista de rutas por vehículo (índices de nodos).
    schedules: lista de cronogramas por vehículo.
    """
    logger.info(f"OR-Tools invoked with {len(cost_matrix)} matrix size, {num_vehicles} vehicles.")
    
    manager = pywrapcp.RoutingIndexManager(
        len(cost_matrix),
        num_vehicles,
        list(range(num_vehicles)),
        list(range(num_vehicles))
    )
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return cost_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # --- CVRPTW: activación condicional ---
    has_service_times = (
        service_times is not None and
        any(st > 0 for st in service_times)
    )
    has_shift_limits = (
        max_shift_minutes_per_vehicle is not None and
        any(limit < 1440 for limit in max_shift_minutes_per_vehicle)
    )
    has_starts = vehicle_start_times is not None
    
    needs_time_dimension = (
        time_windows is not None and
        time_matrix is not None and
        any(tw != (0, 1440) for tw in time_windows)
    ) or has_service_times or has_shift_limits or has_starts

    if needs_time_dimension and time_matrix is not None:
        def time_callback(from_index: int, to_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            transit = time_matrix[from_node][to_node]
            service = service_times[from_node] if service_times and from_node < len(service_times) else 0
            return transit + service

        transit_time_idx = routing.RegisterTransitCallback(time_callback)
        routing.AddDimension(
            transit_time_idx,
            1440,   # slack (permitir esperas hasta fin de jornada)
            1440,   # horizonte: 24h absoluto
            False,  # NO forzar inicio en cero (permite SetValue abajo)
            "Time"
        )
        time_dimension = routing.GetDimensionOrDie("Time")

        # Prioridad 0: Sincronía Temporal absoluta
        for vehicle_id in range(num_vehicles):
            start_min = vehicle_start_times[vehicle_id] if vehicle_start_times and vehicle_id < len(vehicle_start_times) else 0
            start_index = routing.Start(vehicle_id)
            time_dimension.CumulVar(start_index).SetValue(start_min)
            
            # Límite de jornada: start + shift
            if max_shift_minutes_per_vehicle:
                max_shift = max_shift_minutes_per_vehicle[vehicle_id] if vehicle_id < len(max_shift_minutes_per_vehicle) else 480
                end_index = routing.End(vehicle_id)
                time_dimension.CumulVar(end_index).SetMax(start_min + max_shift)

        if time_windows:
            for node_idx, (tw_start, tw_end) in enumerate(time_windows):
                if tw_start == 0 and tw_end == 1440:
                    continue 
                index = manager.NodeToIndex(node_idx)
                if index >= 0:
                    time_dimension.CumulVar(index).SetRange(tw_start, tw_end)
    
    # Capacity Variables Callback (scaled to integers)
    int_demands = [int(v * 1000) for v in demands]
    int_capacities = [int(v * 1000) for v in vehicle_capacities]

    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return int_demands[from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        int_capacities,  # vehicle maximum capacities
        True,  # start cumul to zero
        'Capacity'
    )

    # Disjunctions for dropping unroutable nodes
    cost_array = np.array(cost_matrix)
    real_costs = cost_array[cost_array < UNREACHABLE_PENALTY]
    max_real_cost = int(real_costs.max()) if real_costs.size > 0 else 10**6
    penalty = max_real_cost * 3
    for node in range(num_vehicles, len(cost_matrix)):
        routing.AddDisjunction([manager.NodeToIndex(node)], penalty)

    # Routing Configuration
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

    # Para problemas pequeños, AUTOMATIC es más rápido que GUIDED_LOCAL_SEARCH
    n_nodes = len(cost_matrix)
    if n_nodes <= 10:
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.AUTOMATIC)
    else:
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)

    search_parameters.time_limit.FromSeconds(time_limit_seconds)

    # Execute
    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        logger.warning("No VRP solution could be generated.")
        return None

    # Parse solutions
    routes = []
    schedules = []
    
    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        route = []
        schedule = []
        
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            route.append(node_index)
            
            # Extraer cronograma si existe dimensión Time
            if needs_time_dimension:
                cumul_var = time_dimension.CumulVar(index)
                earliest = solution.Min(cumul_var)
                latest = solution.Max(cumul_var)
                schedule.append({
                    "node_index": node_index,
                    "earliest_arrival_min": earliest,
                    "latest_arrival_min": latest,
                    "suggested_arrival_min": earliest
                })
            else:
                # Sin ventanas: calcular tiempo acumulado desde time_matrix
                schedule.append({
                    "node_index": node_index,
                    "earliest_arrival_min": None,
                    "latest_arrival_min": None,
                    "suggested_arrival_min": None
                })
            
            index = solution.Value(routing.NextVar(index))
        
        routes.append(route)
        schedules.append(schedule)
    
    return routes, schedules

# src/block5/vrp_solver.py
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from typing import List, Optional
import logging

logger = logging.getLogger("VRP_Solver")

def solve_vrp(
    cost_matrix: List[List[int]],
    vehicle_capacities: List[float],
    demands: List[float],
    num_vehicles: int,
    time_limit_seconds: int = 10
) -> Optional[List[List[int]]]:
    """
    Solves the Capacitated Vehicle Routing Problem (CVRP) using OR-Tools.
    Returns a list of routes (each route containing matrix node indices)
    for each vehicle.
    """
    logger.info(f"OR-Tools invoked with {len(cost_matrix)} matrix size, {num_vehicles} vehicles.")
    
    manager = pywrapcp.RoutingIndexManager(
        len(cost_matrix),
        num_vehicles,
        list(range(num_vehicles)),  # Starts are indices 0 to num_vehicles-1
        list(range(num_vehicles))   # Ends are also their own starts
    )
    routing = pywrapcp.RoutingModel(manager)

    # Cost Matrix Callback
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return cost_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    
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
    penalty = 999999998
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
    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        route = []
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            route.append(node_index)
            index = solution.Value(routing.NextVar(index))
        # Optional: route.append(manager.IndexToNode(index)) to display closure
        routes.append(route)

    return routes

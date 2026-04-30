import math
from typing import Dict, Any, List

import polyline

from fuel.models import FuelStation
from fuel.exceptions import UnreachableDestinationError


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in miles between two points 
    on the earth (specified in decimal degrees).
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in miles is approximately 3958.8
    r = 3958.8
    return c * r


class RouteNode:
    """Represents a node in our DAG for dynamic programming."""
    def __init__(self, node_id: str, name: str, mile_marker: float, price: float, station=None):
        self.node_id = node_id
        self.name = name
        self.mile_marker = mile_marker
        self.price = price
        self.station = station  # Reference to the FuelStation DB object if applicable


def calculate_optimal_fuel_stops(route_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculates the optimal sequence of fuel stops to minimize total fuel cost
    using dynamic programming on a Directed Acyclic Graph (DAG).
    
    Args:
        route_data (dict): Dictionary containing 'polyline', 'total_distance_miles', 
                           and 'bounding_box' keys from the routing service.
                           
    Returns:
        dict: A dictionary with 'fuel_stops' list and 'trip_summary' metrics.
        
    Raises:
        UnreachableDestinationError: If distance between required stops exceeds the 500-mile limit.
    """
    # -------------------------------------------------------------------------
    # STEP 1: Decode & Filter
    # -------------------------------------------------------------------------
    encoded_polyline = route_data['polyline']
    total_distance_miles = route_data['total_distance_miles']
    bounding_box = route_data['bounding_box']  # [minLon, minLat, maxLon, maxLat]
    
    # Decode polyline into a list of (latitude, longitude) tuples
    route_coords = polyline.decode(encoded_polyline)
    
    # Extract coordinates to filter stations using Django ORM
    min_lon, min_lat, max_lon, max_lat = bounding_box
    
    # Ensure min/max ordering is strictly correct for Django __range filters
    lat_range = (min(min_lat, max_lat), max(min_lat, max_lat))
    lon_range = (min(min_lon, max_lon), max(min_lon, max_lon))
    
    # Spatial filter: This reduces N from thousands to hundreds extremely fast
    candidate_stations = FuelStation.objects.filter(
        latitude__range=lat_range,
        longitude__range=lon_range
    )
    
    # -------------------------------------------------------------------------
    # STEP 2: Project & Prune (Mile Markers)
    # -------------------------------------------------------------------------
    # Pre-calculate cumulative distances along the route geometry
    path_mile_markers = [0.0]
    for i in range(1, len(route_coords)):
        dist = haversine_distance(
            route_coords[i-1][0], route_coords[i-1][1],
            route_coords[i][0], route_coords[i][1]
        )
        path_mile_markers.append(path_mile_markers[-1] + dist)

    valid_stations = []
    
    # Prune stations that are too far off the route and map valid ones to a mile marker
    for station in candidate_stations:
        min_dist_to_route = float('inf')
        closest_path_idx = -1
        
        # Find the closest point on the route to this station
        for idx, coord in enumerate(route_coords):
            dist = haversine_distance(station.latitude, station.longitude, coord[0], coord[1])
            if dist < min_dist_to_route:
                min_dist_to_route = dist
                closest_path_idx = idx
                
        # Strict constraint: Discard if the station is more than 2.5 miles off the route
        if min_dist_to_route <= 2.5:
            # The station's position along the route is approximately the path distance up to the closest point
            mile_marker = path_mile_markers[closest_path_idx]
            
            # Ensure the station conceptually falls within the start/end bounds
            if mile_marker <= total_distance_miles:
                valid_stations.append({
                    'station': station,
                    'mile_marker': mile_marker,
                    'off_route_dist': min_dist_to_route
                })
            
    # Sort valid stations by their mile marker (distance from the start) to build the DAG
    valid_stations.sort(key=lambda x: x['mile_marker'])
    
    # -------------------------------------------------------------------------
    # STEP 3: Build the DAG & Dynamic Programming
    # -------------------------------------------------------------------------
    nodes: List[RouteNode] = []
    
    # Start Node (Mile 0). 
    # Assumption: Car starts full, meaning no fuel cost to use the first 500 miles.
    nodes.append(RouteNode(node_id="START", name="Start Location", mile_marker=0.0, price=0.0))
    
    # Append the sorted valid station nodes
    for vs in valid_stations:
        station = vs['station']
        nodes.append(RouteNode(
            node_id=str(station.opis_truckstop_id),
            name=station.name,
            mile_marker=vs['mile_marker'],
            price=float(station.retail_price),
            station=station
        ))
        
    # End Node (Mile: total_distance)
    nodes.append(RouteNode(node_id="END", name="Destination", mile_marker=total_distance_miles, price=0.0))
    
    N = len(nodes)
    
    # Initialize minimum cost array and parent tracking array
    min_cost = [float('inf')] * N
    min_cost[0] = 0.0  # Cost to reach the start is 0
    parent = [-1] * N
    
    MPG = 10.0
    MAX_RANGE = 500.0
    
    # DP iteration: Find the minimum cost to reach node i
    for i in range(1, N):
        # Look back at all previous nodes j to see if we can reach i from j
        for j in range(i - 1, -1, -1):
            dist = nodes[i].mile_marker - nodes[j].mile_marker
            
            # Since nodes are sorted, anything further back than j will also be > 500
            if dist > MAX_RANGE:
                break
                
            # Ignore numerical artifacts resulting in negative distances
            if dist < 0:
                continue
                
            # Cost Calculation: 
            # We buy enough fuel at node j's price to cover the exact distance to node i.
            # If node j is START (price=0), this leg is free.
            cost_to_reach = min_cost[j] + ((dist / MPG) * nodes[j].price)
            
            # Update min_cost if this path is cheaper
            if cost_to_reach < min_cost[i]:
                min_cost[i] = cost_to_reach
                parent[i] = j
                
    # -------------------------------------------------------------------------
    # STEP 4: Reconstruct & Format
    # -------------------------------------------------------------------------
    if min_cost[-1] == float('inf'):
        raise UnreachableDestinationError(
            "Cannot reach the destination. The distance between valid fuel stops exceeds the 500-mile max range."
        )
        
    # Backtrack using the parent array to reconstruct the optimal sequence of stops
    path_indices = []
    curr = N - 1
    while curr != -1:
        path_indices.append(curr)
        curr = parent[curr]
        
    path_indices.reverse()
    
    fuel_stops = []
    total_gallons = 0.0
    total_cost = 0.0
    
    # Calculate exact gallons and cost for each chosen leg
    for step in range(len(path_indices) - 1):
        j = path_indices[step]
        i = path_indices[step + 1]
        
        node_j = nodes[j]
        node_i = nodes[i]
        
        dist = node_i.mile_marker - node_j.mile_marker
        gallons_needed = dist / MPG
        cost_for_leg = gallons_needed * node_j.price
        
        total_gallons += gallons_needed
        total_cost += cost_for_leg
        
        # We only log actual stops (not the START node)
        if node_j.station is not None:
            fuel_stops.append({
                'opis_truckstop_id': node_j.station.opis_truckstop_id,
                'name': node_j.name,
                'location': f"{node_j.station.city}, {node_j.station.state}",
                'mile_marker': round(node_j.mile_marker, 2),
                'price_per_gallon': round(node_j.price, 3),
                'gallons_purchased': round(gallons_needed, 2),
                'cost': round(cost_for_leg, 2)
            })
            
    return {
        'fuel_stops': fuel_stops,
        'trip_summary': {
            'total_gallons_consumed': round(total_gallons, 2),
            'total_fuel_cost': round(total_cost, 2),
            'total_route_distance_miles': round(total_distance_miles, 2)
        }
    }

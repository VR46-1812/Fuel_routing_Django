import logging
import time
from typing import Dict, Any, Tuple

import requests
from django.conf import settings

from .exceptions import GeocodingError, RouteNotFoundError, RoutingAPIError

logger = logging.getLogger(__name__)

def _geocode_address(address: str) -> Tuple[float, float]:
    """
    Geocodes an address string to (longitude, latitude) coordinates.
    OpenRouteService expects coordinates in [lon, lat] order.
    """
    url = "https://photon.komoot.io/api/"
    params = {
        'q': address,
        'limit': 1
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        # Basic rate limiting
        time.sleep(1.0)
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        features = data.get('features', [])
        if features:
            coords = features[0]['geometry']['coordinates']
            # Photon returns [longitude, latitude], which is exactly what we need
            return float(coords[0]), float(coords[1])
        raise GeocodingError(f"No coordinates found for address: '{address}'")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during geocoding for '{address}': {str(e)}")
        raise GeocodingError(f"Network error geocoding '{address}'") from e
    except (IndexError, ValueError, KeyError, TypeError) as e:
        logger.error(f"Data extraction error during geocoding for '{address}': {str(e)}")
        raise GeocodingError(f"Invalid data received while geocoding '{address}'") from e


def fetch_route_geometry(start_address: str, end_address: str) -> Dict[str, Any]:
    """
    Fetches the route geometry and details between two addresses using OpenRouteService.
    
    Args:
        start_address: The starting location string.
        end_address: The destination location string.
        
    Returns:
        dict: Containing 'total_distance_miles', 'polyline', and 'bounding_box'.
        
    Raises:
        GeocodingError: If address resolution fails.
        RoutingAPIError: If the ORS API call fails or times out.
        RouteNotFoundError: If no route is found between the two points.
    """
    # 1. Geocode both addresses
    try:
        start_coords = _geocode_address(start_address)
        end_coords = _geocode_address(end_address)
    except GeocodingError as e:
        logger.error(f"Route generation failed during geocoding: {str(e)}")
        raise

    # 2. Get API key from Django settings
    api_key = getattr(settings, 'OPENROUTESERVICE_API_KEY', None)
    if not api_key:
        logger.error("OPENROUTESERVICE_API_KEY is not set in Django settings.")
        raise RoutingAPIError("Server configuration error: Missing routing API key.")

    # 3. Call OpenRouteService Directions API
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {
        'Authorization': api_key,
        'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8',
        'Content-Type': 'application/json; charset=utf-8'
    }
    
    # ORS expects coordinates as a list of [lon, lat] pairs
    payload = {
        "coordinates": [list(start_coords), list(end_coords)]
    }
    
    try:
        # Timeouts are critical when communicating with external routing providers
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        # Handle specific API errors gracefully
        if response.status_code in (404, 400):
            logger.warning(f"ORS could not find route: {response.text}")
            raise RouteNotFoundError(f"No valid driving route found between {start_address} and {end_address}")
            
        response.raise_for_status()
        data = response.json()
        
        # 4. Extract required routing data
        routes = data.get('routes', [])
        if not routes:
            raise RouteNotFoundError("API returned successful response but no routes were found.")
            
        route = routes[0]
        summary = route.get('summary', {})
        
        distance_meters = summary.get('distance', 0)
        # Convert meters to miles
        distance_miles = distance_meters * 0.000621371
        
        polyline = route.get('geometry', '')
        bounding_box = route.get('bbox', [])
        
        if not polyline or not bounding_box:
            raise RoutingAPIError("API response is missing required 'geometry' or 'bbox' fields.")
            
        return {
            'total_distance_miles': round(distance_miles, 2),
            'polyline': polyline,
            'bounding_box': bounding_box  # Format typically [minLon, minLat, maxLon, maxLat]
        }
        
    except requests.exceptions.Timeout as e:
        logger.error(f"Routing API timeout for route {start_address} to {end_address}: {str(e)}")
        raise RoutingAPIError("The routing service took too long to respond. Please try again later.") from e
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Routing API request failed: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"API Response content: {e.response.text}")
        raise RoutingAPIError("Failed to communicate with the OpenRouteService API.") from e
        
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error parsing Routing API response: {str(e)}")
        raise RoutingAPIError("Received an invalid response format from the routing service.") from e

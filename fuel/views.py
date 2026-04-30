import hashlib
import logging

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RouteOptimizationRequestSerializer
from .services import fetch_route_geometry
from .optimizer import calculate_optimal_fuel_stops
from .exceptions import (
    GeocodingError,
    RouteNotFoundError,
    RoutingAPIError,
    UnreachableDestinationError
)

logger = logging.getLogger(__name__)

class OptimizeRouteView(APIView):
    """
    API View to calculate the optimal fuel stops between two locations.
    Implements caching and custom error handling to ensure production readiness.
    """
    
    def post(self, request, *args, **kwargs):
        # 1. Validate incoming request
        serializer = RouteOptimizationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request payload.", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        start_location = serializer.validated_data['start_location']
        finish_location = serializer.validated_data['finish_location']
        
        # 2. Generate a deterministic cache key
        # Using MD5 hash to safely handle spaces, special characters, or long address strings
        raw_key = f"{start_location.strip().lower()}_{finish_location.strip().lower()}"
        key_hash = hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        cache_key = f"route_opt_{key_hash}"
        
        # 3. Check cache
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for route: {start_location} -> {finish_location}")
            # Inject a meta flag for the frontend to know the response was cached
            cached_result['meta'] = {'cached': True}
            return Response(cached_result, status=status.HTTP_200_OK)
            
        logger.info(f"Cache miss for route: {start_location} -> {finish_location}. Computing...")
        
        # 4. Perform complex route & optimization calculation with robust error handling
        try:
            # a. Fetch route geometry and bounding box from the external OpenRouteService
            route_data = fetch_route_geometry(start_location, finish_location)
            
            # b. Run dynamic programming algorithm to find optimal fuel stops
            optimization_result = calculate_optimal_fuel_stops(route_data)
            
            # c. Structure the final payload (Combining routing geometry with stops)
            final_payload = {
                'start_location': start_location,
                'finish_location': finish_location,
                'route_geometry_polyline': route_data['polyline'],
                'fuel_stops': optimization_result['fuel_stops'],
                'trip_summary': optimization_result['trip_summary']
            }
            
            # d. Save to cache with a 24-hour TTL (86400 seconds)
            cache.set(cache_key, final_payload, timeout=86400)
            
            # e. Return fresh Response
            final_payload['meta'] = {'cached': False}
            return Response(final_payload, status=status.HTTP_200_OK)
            
        except (GeocodingError, RouteNotFoundError, UnreachableDestinationError) as e:
            # These represent user-facing logical errors (e.g., bad address, unroutable points)
            logger.warning(f"Route calculation failed (Bad Request): {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except RoutingAPIError as e:
            # These represent downstream dependency failures (OpenRouteService is down)
            logger.error(f"Routing Service Error (Bad Gateway): {str(e)}")
            return Response(
                {"error": "Our routing provider is currently unavailable. Please try again later."},
                status=status.HTTP_502_BAD_GATEWAY
            )
            
        except Exception as e:
            # Catch-all for unexpected internal crashes to prevent raw 500 HTML stacks
            logger.exception(f"Unexpected error during optimization: {str(e)}")
            return Response(
                {"error": "An unexpected error occurred processing your route."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

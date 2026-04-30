class FuelRouteException(Exception):
    """Base exception for the Fuel Route project."""
    pass

class RoutingAPIError(FuelRouteException):
    """Raised when there is a communication or unexpected error with the external Routing API."""
    pass

class RouteNotFoundError(FuelRouteException):
    """Raised when the routing service cannot find a valid route between points."""
    pass

class GeocodingError(FuelRouteException):
    """Raised when an address cannot be converted to coordinates."""
    pass

class UnreachableDestinationError(FuelRouteException):
    """Raised when it is impossible to reach the destination with the given constraints (e.g., fuel range)."""
    pass

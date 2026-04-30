from rest_framework import serializers

class RouteOptimizationRequestSerializer(serializers.Serializer):
    """
    Validates incoming payload for route optimization requests.
    Requires both start_location and finish_location to be provided.
    """
    start_location = serializers.CharField(
        required=True, 
        max_length=500,
        help_text="The starting address or city, state (e.g., 'Los Angeles, CA')"
    )
    finish_location = serializers.CharField(
        required=True, 
        max_length=500,
        help_text="The destination address or city, state (e.g., 'New York, NY')"
    )

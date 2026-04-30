from django.db import models

class FuelStation(models.Model):
    """
    Model representing a fuel station/truck stop.
    """
    opis_truckstop_id = models.IntegerField(
        unique=True, 
        help_text="OPIS Truckstop ID from the CSV data"
    )
    name = models.CharField(max_length=255, help_text="Truckstop Name")
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.IntegerField(help_text="Rack ID")
    retail_price = models.DecimalField(
        max_digits=8, 
        decimal_places=3, 
        help_text="Retail Price"
    )
    
    # Spatial coordinates
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        app_label = 'fuel'
        db_table = "fuel_station"
        indexes = [
            # Index on spatial coordinates for bounding-box queries
            models.Index(fields=['latitude', 'longitude'], name='idx_station_lat_lon'),
            # Index on state for filtering
            models.Index(fields=['state'], name='idx_station_state'),
        ]

    def __str__(self) -> str:
        return f"{self.name} - {self.city}, {self.state} ({self.opis_truckstop_id})"

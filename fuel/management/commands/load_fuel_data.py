import csv
import logging
import time
from typing import Optional, Tuple, List

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from fuel.models import FuelStation

logger = logging.getLogger(__name__)

def geocode_address(city: str, state: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Geocodes a city and state to latitude and longitude.
    Mockable function currently using the open Photon API.
    """
    query = f"{city}, {state}, USA"
    url = "https://photon.komoot.io/api/"
    params = {
        'q': query,
        'limit': 1
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        # Optimized rate limiting to match Photon's tolerance
        time.sleep(0.3)
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        features = data.get('features', [])
        if features:
            coords = features[0]['geometry']['coordinates']
            # Photon returns [longitude, latitude], we return (lat, lon)
            return float(coords[1]), float(coords[0])
    except requests.RequestException as e:
        logger.warning(f"Geocoding network error for {query}: {e}")
    except (IndexError, ValueError, KeyError, TypeError) as e:
        logger.warning(f"Geocoding data extraction error for {query}: {e}")
        
    return None, None


class Command(BaseCommand):
    help = 'Ingestion of fuel station CSV data into the database.'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file', 
            type=str, 
            nargs='?',
            default='data/fuel_prices_clean.csv',
            help='Absolute or relative path to the CSV file to be loaded. Defaults to data/fuel_prices_clean.csv'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Number of records to bulk create at a time.'
        )

    def handle(self, *args, **kwargs):
        csv_file_path = kwargs['csv_file']
        batch_size = kwargs['batch_size']

        # Clear the Database to ensure a clean slate and prevent Unique Constraint collisions
        self.stdout.write(self.style.WARNING("Clearing existing data..."))
        FuelStation.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("Cleared existing data."))

        self.stdout.write(self.style.SUCCESS(f"Starting ingestion from {csv_file_path}..."))

        stations_to_create: List[FuelStation] = []
        
        # City cache to dramatically speed up ingestion and avoid API bans
        city_cache = {}

        try:
            with open(csv_file_path, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                for row_num, row in enumerate(reader, start=1):
                    # Progress Tracking
                    if row_num % 100 == 0:
                        self.stdout.write(f"Processed {row_num} stations...")
                        
                    try:
                        opis_id = int(row['OPIS Truckstop ID'])
                        name = row['Truckstop Name']
                        address = row['Address']
                        city = row['City']
                        state = row['State']
                        retail_price = float(row['Retail Price'])
                        
                        # Fallback Rack ID since it's dropped from the clean dataset but required by the model
                        rack_id = 0
                    except (KeyError, ValueError) as e:
                        self.stderr.write(
                            self.style.WARNING(f"Row {row_num} skipped: Invalid or missing data - {e}")
                        )
                        continue

                    # Geocode the address using the city cache
                    cache_key = (city, state)
                    if cache_key in city_cache:
                        lat, lon = city_cache[cache_key]
                    else:
                        lat, lon = geocode_address(city, state)
                        city_cache[cache_key] = (lat, lon)
                        
                    # Graceful Fallback: skip saving this station if coordinates couldn't be resolved
                    if lat is None or lon is None:
                        self.stderr.write(
                            self.style.WARNING(f"Skipping OPIS ID {opis_id} - {name} due to missing coordinates.")
                        )
                        continue

                    station_data = {
                        'opis_truckstop_id': opis_id,
                        'name': name,
                        'address': address,
                        'city': city,
                        'state': state,
                        'rack_id': rack_id,
                        'retail_price': retail_price,
                        'latitude': lat,
                        'longitude': lon,
                    }

                    stations_to_create.append(FuelStation(**station_data))

                    # Execute bulk create in chunks
                    if len(stations_to_create) >= batch_size:
                        self._bulk_insert(stations_to_create)
                        stations_to_create.clear()

                # Process remaining records in the final chunk
                if stations_to_create:
                    self._bulk_insert(stations_to_create)

            self.stdout.write(self.style.SUCCESS('Successfully loaded all fuel station data.'))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {csv_file_path}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred during ingestion: {str(e)}"))

    def _bulk_insert(self, stations: List[FuelStation]) -> None:
        """Helper method to bulk insert a list of FuelStation records safely."""
        try:
            with transaction.atomic():
                FuelStation.objects.bulk_create(stations)
            self.stdout.write(f"Bulk created {len(stations)} new records.")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to bulk create records: {str(e)}"))

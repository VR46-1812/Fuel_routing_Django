# Fuel Optimization API

This project provides a robust, caching-enabled REST API that calculates the optimal fuel stops for a vehicle traveling across the US. It adheres to a strict 500-mile maximum vehicle range while aiming to minimize total fuel costs using a Dynamic Programming algorithm.

## Setup Instructions

### 1. Configure Environment Variables
Create a `.env` file in the root directory and add your OpenRouteService API key. This key is securely injected into the container via Docker Compose.

```env
OPENROUTESERVICE_API_KEY=your_actual_api_key_here
```

### 2. Build and Start the Infrastructure
Use Docker Compose to build the web container and start both the Django application and the Redis cache service:

```bash
docker-compose up --build
```

*(You can add `-d` to run it in detached mode).*

### 3. Ingest Fuel Station Data
Once the containers are running successfully, you need to ingest the initial CSV data into the SQLite database. Open a new terminal session and run the custom, idempotent Django management command inside the `web` container:

```bash
docker-compose exec web python manage.py load_fuel_data data/fuel-prices-for-be-assessment.csv
```
*(Ensure that your CSV is located in the `data/` folder relative to the project root, or modify the path in the command above accordingly).*

### 4. Test the API
The API is now fully operational and listening on port 8000. You can test the endpoint using `curl`, Postman, or Insomnia.

```bash
curl -X POST http://localhost:8000/api/fuel/optimize-route/ \
     -H "Content-Type: application/json" \
     -d '{
           "start_location": "Los Angeles, CA",
           "finish_location": "New York, NY"
         }'
```

**Expected Result:**
You will receive a highly structured JSON response detailing the geometry of the route (`polyline`), the optimal sequence of fuel stops (`fuel_stops`), and a trip summary including total distance, total gallons, and total cost. 

**Note on Performance:** 
The first request for a given route may take a few seconds due to external OpenRouteService routing and internal spatial/DP computation. Subsequent requests for the exact same start and finish locations will return nearly instantly thanks to the configured 24-hour Redis caching layer.

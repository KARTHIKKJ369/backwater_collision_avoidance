# API Documentation

Base URL: `http://localhost:8000`

Interactive docs are available at `/docs` after startup.

## Endpoints

### GET /boats

Returns registered boats.

### GET /telemetry

Query parameters:

- `boat_id`: optional boat filter
- `limit`: default `200`

Returns telemetry rows.

### GET /alerts

Query parameters:

- `limit`: default `100`

Returns recent warning and danger alerts.

### POST /predict

Request:

```json
{
  "boat_id": "B01"
}
```

Response:

```json
{
  "boat_id": "B01",
  "triggered": true,
  "positions": [
    { "lat": 9.5911, "lon": 76.5222, "confidence": 0.55 }
  ]
}
```

## Additional Dashboard Endpoints

### GET /health

Returns backend health.

### GET /telemetry/latest

Returns the latest position for each boat.

### GET /predictions

Returns stored future positions.

### GET /metrics

Response:

```json
{
  "predictions_total": 0,
  "alerts_total": 0,
  "collisions_predicted": 0,
  "avg_prediction_latency_ms": 0,
  "avg_risk": 0,
  "prediction_skipped": 0,
  "prediction_executed": 0
}
```

### POST /telemetry

Direct ingestion endpoint for tests without MQTT.

Request:

```json
{
  "boat_id": "B01",
  "timestamp": 0,
  "lat": 9.591,
  "lon": 76.522,
  "speed": 4.2,
  "heading": 65,
  "obstacle": 0
}
```

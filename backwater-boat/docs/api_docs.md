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

### GET /recommendations

Returns cooperative avoidance recommendations.

Response:

```json
[
  {
    "boat_id": "B01",
    "action": "TURN_RIGHT",
    "accepted": 0,
    "alert_state": "WARNING"
  }
]
```

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
  "prediction_executed": 0,
  "warnings": 0,
  "recommendations": 0,
  "accepted_actions": 0,
  "avoided_collisions": 0
}
```

### GET /evaluation

Computes evaluation metrics from alerts, predictions, and telemetry, then writes `results/evaluation.csv`, `results/{scenario}.csv`, and `results/summary.json`.

Query parameters:

- `scenario`: optional, defaults to `LIVE`

Response:

```json
{
  "precision": 0,
  "recall": 0,
  "f1": 0,
  "false_alarm_rate": 0,
  "avg_ttc": 0
}
```

### GET /timeline

Returns scenario timeline samples for charting and export.

Query parameters:

- `scenario`: optional, defaults to `LIVE`

Response:

```json
[
  {
    "t": 0,
    "distance": 100,
    "future_distance": 45,
    "risk": 0.72,
    "ttc": 6.2,
    "prediction": 1,
    "alert": "DANGER"
  }
]
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

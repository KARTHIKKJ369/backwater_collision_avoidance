# Architecture

The project is modular so hardware can be introduced after the simulator has proven the data path.

## Modules

```text
simulator/boat_sim.py
  publishes JSON telemetry to boats/{id}/sensor

mosquitto
  MQTT broker for simulated and real LoRa gateway data

backend/mqtt/mqtt_client.py
  subscribes to telemetry, stores messages, publishes status and alerts

backend/database
  SQLite schema and persistence helpers

backend/risk_engine/risk_engine.py
  computes distance, relative speed, heading difference, and warning level

backend/risk_engine/ttc.py
  computes time to collision and TTC state

backend/risk_engine/predictive_collision.py
  compares future paths and classifies future collision state

backend/risk_engine/alerts.py
  deduplicates alerts with SAFE, WARNING, and DANGER transitions

backend/predict_controller.py
  gates prediction execution and tracks prediction metrics

ml/training
  creates synthetic trajectory data and trains model.h5

ml/inference
  loads model.h5 when available and falls back to dead reckoning

dashboard
  React Leaflet dashboard for live boats, predictions, alerts, telemetry, and history
```

## MQTT Topics

- `boats/{id}/sensor`
- `boats/{id}/predict`
- `boats/{id}/alert`
- `boats/{id}/status`

## Risk Engine

Risk score:

```text
risk = 0.4 * trajectory + 0.3 * distance + 0.2 * heading + 0.1 * obstacle
```

Thresholds:

- `risk < 0.4`: SAFE
- `0.4 <= risk <= 0.7`: WARNING
- `risk > 0.7`: DANGER

## Prediction Trigger

Prediction runs when:

- Distance is under 150 meters, or
- Risk is greater than 0.3

The Raspberry Pi target uses the trained `ml/model.h5`. The software prototype uses a deterministic fallback until the model is trained.

## Predictive Collision

Predicted trajectories are compared step by step. The smallest future separation decides alert state:

- `future_distance > 100`: SAFE
- `50 <= future_distance <= 100`: WARNING
- `future_distance < 50`: DANGER

Alerts are persisted only when state changes, with a 10 second cooldown.

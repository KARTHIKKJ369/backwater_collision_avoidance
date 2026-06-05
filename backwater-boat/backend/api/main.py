from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.database import db
from backend.evaluation import evaluate, timeline as evaluation_timeline
from backend.mqtt.mqtt_client import publish, store_message, subscribe
from backend.predict_controller import manual_prediction, metrics as prediction_metrics
from backend.weather.weather_client import get_weather_for_position, mock_weather

app = FastAPI(title="Backwater Boat Collision Avoidance API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TelemetryIn(BaseModel):
    boat_id: str
    timestamp: float = Field(default_factory=lambda: time.time())
    lat: float
    lon: float
    speed: float
    heading: float
    obstacle: int = 0
    scenario: str = "LIVE"


class PredictIn(BaseModel):
    boat_id: str


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    subscribe()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/boats")
def boats() -> list[dict[str, Any]]:
    return db.fetch_all("boats")


@app.get("/telemetry")
def telemetry(boat_id: str | None = None, limit: int = Query(200, ge=1, le=1000)) -> list[dict[str, Any]]:
    if boat_id:
        return db.telemetry_for_boat(boat_id, limit)
    return db.fetch_all("telemetry", limit)


@app.get("/telemetry/latest")
def latest_telemetry() -> list[dict[str, Any]]:
    return db.latest_telemetry()


@app.post("/telemetry")
def ingest_telemetry(payload: TelemetryIn) -> dict[str, Any]:
    result = store_message(payload.model_dump())
    return {"status": "stored", **result}


@app.get("/alerts")
def alerts(limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    return db.fetch_all("alerts", limit)


@app.get("/predictions")
def predictions(limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    return db.fetch_all("prediction", limit)


@app.get("/recommendations")
def recommendations(limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    return db.fetch_all("recommendations", limit)


@app.post("/predict")
def predict(payload: PredictIn) -> dict[str, Any]:
    result = manual_prediction(payload.boat_id)
    positions = result["positions"]
    publish(f"boats/{payload.boat_id}/predict", {"boat_id": payload.boat_id, "positions": positions})
    return {"boat_id": payload.boat_id, "triggered": result["executed"], **result}


@app.get("/metrics")
def metrics() -> dict[str, float | int]:
    prediction = prediction_metrics()
    return {
        "predictions_total": prediction["prediction_executed"],
        "alerts_total": db.count_rows("alerts"),
        "collisions_predicted": prediction["collisions_predicted"],
        "avg_prediction_latency_ms": prediction["avg_prediction_latency_ms"],
        "avg_risk": db.average_risk(),
        "prediction_skipped": prediction["prediction_skipped"],
        "prediction_executed": prediction["prediction_executed"],
        "warnings": prediction["warnings"],
        "recommendations": prediction["recommendations"],
        "accepted_actions": prediction["accepted_actions"],
        "avoided_collisions": prediction["avoided_collisions"],
    }


@app.get("/evaluation")
def evaluation(scenario: str = "LIVE") -> dict[str, float | int | str]:
    return evaluate(scenario)


@app.get("/timeline")
def timeline(scenario: str = "LIVE") -> list[dict[str, float | int | str | None]]:
    return evaluation_timeline(scenario)


@app.get("/weather")
def weather(lat: float, lon: float) -> dict[str, Any]:
    """
    Return live OpenWeatherMap data for a position.
    Falls back to a CLEAR mock when OPENWEATHER_API_KEY is not set.
    """
    data = get_weather_for_position(lat, lon)
    if data is None:
        data = mock_weather("CLEAR")
        data["source"] = "mock"
    else:
        data["source"] = "openweathermap"
    return data


@app.get("/weather/mock")
def weather_mock(preset: str = "CLEAR") -> dict[str, Any]:
    """
    Return a mock weather preset for offline testing.
    Presets: CLEAR, FOG, RAIN, STORM
    """
    data = mock_weather(preset)
    data["source"] = "mock"
    return data
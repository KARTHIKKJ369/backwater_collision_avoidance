from __future__ import annotations

import math
import random
import threading
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

# ---------------------------------------------------------------------------
# Built-in scenario engine — mirrors simulator/scenarios/*.py so the backend
# can drive a demo without the separate simulator container being active.
# ---------------------------------------------------------------------------

def _step(s: dict) -> None:
    """Advance position and derive IMU channels for one 1-second tick.

    Mirrors BoatState.step() in simulator/boat_sim.py so the ML model
    receives the same 11-feature input it was trained on instead of zeroed
    IMU values that degrade prediction quality (especially on turns and
    deceleration events like BLIND_TURN and SUDDEN_STOP).
    """
    # IMU — derived from kinematic deltas (DT = 1 s)
    prev_speed   = s.get("_prev_speed",   s["speed"])
    prev_heading = s.get("_prev_heading", s["heading"])

    s["ax"] = round(s["speed"] - prev_speed, 4)                         # forward accel
    delta_h = (s["heading"] - prev_heading + 180) % 360 - 180
    s["gz"] = round(math.radians(delta_h), 4)                           # yaw rate rad/s
    s["ay"] = round(s["speed"] * s["gz"], 4)                            # centripetal m/s²
    s["az"] = round(9.81 + random.gauss(0, 0.05), 4)                    # gravity + heave
    s["gx"] = round(random.gauss(0, 0.02), 5)                           # wave roll
    s["gy"] = round(random.gauss(0, 0.02), 5)                           # wave pitch

    s["_prev_speed"]   = s["speed"]
    s["_prev_heading"] = s["heading"]

    # Advance position (flat-earth, valid for short ranges)
    rad = math.radians(s["heading"])
    s["lat"] += (s["speed"] * math.cos(rad)) / 111_320
    s["lon"] += (s["speed"] * math.sin(rad)) / (
        111_320 * math.cos(math.radians(s["lat"]))
    )


def _update_head_on(states: list[dict], tick: int) -> None:
    for s in states:
        s["speed"] = 8.0


def _update_crossing(states: list[dict], tick: int) -> None:
    if tick > 30:
        for s in states:
            if s["boat_id"] == "B02":
                s["heading"] -= 0.4


def _update_blind_turn(states: list[dict], tick: int) -> None:
    for s in states:
        if s["boat_id"] == "B01":
            s["heading"] += 1.4
        else:
            s["heading"] -= 1.2


def _update_sudden_stop(states: list[dict], tick: int) -> None:
    if tick > 15:
        states[1]["speed"] = max(0.0, states[1]["speed"] - 0.8)


SCENARIOS: dict[str, dict[str, Any]] = {
    "HEAD_ON": {
        "label": "Head-On",
        "description": "Two boats at full speed on a direct collision course. Triggers DANGER within ~10 s.",
        "duration": 60,
        "states": [
            {"boat_id": "B01", "lat": 9.5910, "lon": 76.5211, "speed": 8.0, "heading": 90, "obstacle": 0},
            {"boat_id": "B02", "lat": 9.5910, "lon": 76.5240, "speed": 8.0, "heading": 270, "obstacle": 0},
        ],
        "update": _update_head_on,
    },
    "CROSSING": {
        "label": "Crossing",
        "description": "Boats on intersecting courses; B02 slowly turns away after tick 30.",
        "duration": 80,
        "states": [
            {"boat_id": "B01", "lat": 9.5910, "lon": 76.5214, "speed": 4.6, "heading": 85, "obstacle": 0},
            {"boat_id": "B02", "lat": 9.5904, "lon": 76.5228, "speed": 4.4, "heading": 350, "obstacle": 0},
        ],
        "update": _update_crossing,
    },
    "BLIND_TURN": {
        "label": "Blind Turn",
        "description": "Both boats emerge from a blind canal bend, converging toward each other.",
        "duration": 70,
        "states": [
            {"boat_id": "B01", "lat": 9.5907, "lon": 76.5211, "speed": 3.8, "heading": 30, "obstacle": 1},
            {"boat_id": "B02", "lat": 9.5919, "lon": 76.5220, "speed": 3.5, "heading": 215, "obstacle": 1},
        ],
        "update": _update_blind_turn,
    },
    "SUDDEN_STOP": {
        "label": "Sudden Stop",
        "description": "B01 follows B02 closely; B02 decelerates sharply at tick 15.",
        "duration": 60,
        "states": [
            {"boat_id": "B01", "lat": 9.5910, "lon": 76.5216, "speed": 6.0, "heading": 80, "obstacle": 0},
            {"boat_id": "B02", "lat": 9.5911, "lon": 76.5220, "speed": 5.8, "heading": 80, "obstacle": 0},
        ],
        "update": _update_sudden_stop,
    },
}

_sim_lock = threading.Lock()
_sim_thread: threading.Thread | None = None
_sim_stop = threading.Event()
_sim_status: dict[str, Any] = {"running": False, "scenario": None, "tick": 0}


def _scenario_loop(name: str, stop: threading.Event) -> None:
    """Background thread: tick the scenario and publish MQTT sensor payloads."""
    defn = SCENARIOS[name]
    states = [dict(s) for s in defn["states"]]  # deep-copy so originals stay clean
    tick = 0
    while not stop.is_set() and tick < defn["duration"]:
        defn["update"](states, tick)
        for s in states:
            _step(s)
            payload: dict[str, Any] = {
                "boat_id":   s["boat_id"],
                "timestamp": time.time(),
                "lat":       round(s["lat"], 7),
                "lon":       round(s["lon"], 7),
                "speed":     round(s["speed"], 2),
                "heading":   round(s["heading"] % 360, 2),
                "obstacle":  s.get("obstacle", 0),
                "scenario":  name,
                # IMU channels — computed by _step(), required for 11-feature ML input
                "ax": s.get("ax", 0.0),
                "ay": s.get("ay", 0.0),
                "az": s.get("az", 9.81),
                "gx": s.get("gx", 0.0),
                "gy": s.get("gy", 0.0),
                "gz": s.get("gz", 0.0),
            }
            publish(f"boats/{s['boat_id']}/sensor", payload)
        with _sim_lock:
            _sim_status["tick"] = tick
        tick += 1
        stop.wait(1.0)
    with _sim_lock:
        _sim_status.update({"running": False, "scenario": None, "tick": 0})


# ---------------------------------------------------------------------------

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
    # latest_predictions() returns only the most-recent batch per boat, not
    # the last N rows across all ticks (which would cause the fan-of-lines bug).
    return db.latest_predictions()


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


@app.post("/boats/{boat_id}/ack")
def ack_recommendation(boat_id: str, payload: dict[str, Any] = {}) -> dict[str, Any]:
    """Mark a recommendation as accepted and publish the ack to MQTT."""
    action = str(payload.get("action", ""))
    rec_id = db.mark_recommendation_accepted(boat_id, action)
    publish(f"boats/{boat_id}/ack", {"boat_id": boat_id, "action": action, "accepted": True})
    return {"boat_id": boat_id, "accepted": True, "recommendation_id": rec_id}


@app.get("/scenarios")
def list_scenarios() -> list[dict[str, Any]]:
    """Return metadata for every built-in demo scenario."""
    return [
        {
            "id": key,
            "label": val["label"],
            "description": val["description"],
            "duration": val["duration"],
            "boats": [s["boat_id"] for s in val["states"]],
        }
        for key, val in SCENARIOS.items()
    ]


@app.get("/scenarios/status")
def scenario_status() -> dict[str, Any]:
    """Return whether a scenario is currently running and how far along it is."""
    with _sim_lock:
        status = dict(_sim_status)
    if status["running"] and status["scenario"]:
        status["duration"] = SCENARIOS[status["scenario"]]["duration"]
    return status


@app.post("/scenarios/{name}/run")
def run_scenario(name: str) -> dict[str, Any]:
    """Start a built-in demo scenario, stopping any currently running one first."""
    global _sim_thread, _sim_stop
    name = name.upper()
    if name not in SCENARIOS:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {name}")

    # --- Thread-safe swap -------------------------------------------------------
    # FastAPI runs sync endpoints in a thread pool, so two rapid requests can
    # execute concurrently.  Without the lock, both could pass the join() and
    # each create a new thread — leaving two _scenario_loop threads alive at
    # once and publishing sensor data simultaneously (the "both run turn by turn"
    # symptom).  We capture old_stop/old_thread under the lock so that only ONE
    # new thread is ever registered at a time, then do the slow join() outside
    # the lock to avoid blocking other requests.
    with _sim_lock:
        old_stop: threading.Event = _sim_stop
        old_thread: threading.Thread | None = _sim_thread

        _sim_stop = threading.Event()
        new_stop = _sim_stop

        _sim_status.update({"running": True, "scenario": name, "tick": 0})

        new_thread = threading.Thread(
            target=_scenario_loop, args=(name, new_stop), daemon=True, name=f"sim-{name}"
        )
        _sim_thread = new_thread
    # ---------------------------------------------------------------------------

    # Signal the old scenario to stop and wait for it to exit cleanly (outside
    # the lock so stop/status endpoints aren't blocked during the join).
    old_stop.set()
    if old_thread and old_thread.is_alive():
        old_thread.join(timeout=3)

    new_thread.start()
    return {"started": True, "scenario": name}


@app.post("/scenarios/stop")
def stop_scenario() -> dict[str, Any]:
    """Stop whatever scenario is currently running."""
    _sim_stop.set()
    with _sim_lock:
        _sim_status.update({"running": False, "scenario": None, "tick": 0})
    return {"stopped": True}


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
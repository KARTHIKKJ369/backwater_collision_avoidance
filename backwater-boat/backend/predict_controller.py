from __future__ import annotations

import time
from statistics import mean
from typing import Any

from backend.database import db
from backend.risk_engine.predictive_collision import predict_collision
from ml.inference.predict import predict_future_positions

prediction_skipped = 0
prediction_executed = 0
collisions_predicted = 0
warnings = 0
recommendations = 0
accepted_actions = 0
avoided_collisions = 0
_prediction_latencies_ms: list[float] = []
# Tracks the last alert_state seen for each pair key so we only count a
# collision event once per distinct SAFE→non-SAFE transition, not once per
# tick while the pair remains in a danger state.
_pair_collision_state: dict[str, str] = {}


def should_run_prediction(distance_m: float, risk: float, ttc: float | None = None) -> bool:
    # Aligned with README: trigger at 150 m, TTC < 15 s, or risk > 0.3.
    # Previous thresholds (80 m / 0.5) were too conservative and caused
    # CROSSING and SUDDEN_STOP to skip prediction entirely, producing
    # zero DANGER alerts and 0.0 precision/F1 for those scenarios.
    return distance_m < 150 or (ttc is not None and ttc < 15) or risk > 0.3


def run_prediction(boat_id: str, scenario: str = "LIVE") -> dict[str, Any]:
    global prediction_executed
    started = time.perf_counter()
    history = db.telemetry_for_boat(boat_id, 10)
    positions = predict_future_positions(history)
    timestamp = time.time()

    for point in positions:
        db.insert_prediction(boat_id, timestamp, point["lat"], point["lon"], point["confidence"], scenario)

    latency_ms = (time.perf_counter() - started) * 1000
    _prediction_latencies_ms.append(latency_ms)
    prediction_executed += 1
    return {"boat_id": boat_id, "executed": True, "positions": positions, "latency_ms": round(latency_ms, 2)}


def skip_prediction(boat_id: str, reason: str) -> dict[str, Any]:
    global prediction_skipped
    prediction_skipped += 1
    return {"boat_id": boat_id, "executed": False, "positions": [], "reason": reason}


def run_prediction_if_needed(
    boat_id: str,
    distance_m: float,
    risk: float,
    ttc: float | None = None,
    scenario: str = "LIVE",
) -> dict[str, Any]:
    if should_run_prediction(distance_m, risk, ttc):
        return run_prediction(boat_id, scenario)
    return skip_prediction(boat_id, "distance>=150, ttc>=15, and risk<=0.3")


def evaluate_pair(
    boat_a: str,
    boat_b: str,
    distance_m: float,
    risk: float,
    ttc: float | None = None,
    scenario: str = "LIVE",
) -> dict[str, Any]:
    global collisions_predicted
    prediction_a = run_prediction_if_needed(boat_a, distance_m, risk, ttc, scenario)
    prediction_b = run_prediction_if_needed(boat_b, distance_m, risk, ttc, scenario)

    if not prediction_a["executed"] or not prediction_b["executed"]:
        return {
            "executed": False,
            "prediction_a": prediction_a,
            "prediction_b": prediction_b,
            "collision": None,
        }

    collision = predict_collision(prediction_a["positions"], prediction_b["positions"])
    new_state = collision["alert_state"]

    # Count a collision event only when this pair transitions into a non-SAFE
    # state — not on every tick while it stays in that state.
    pair_key = ":".join(sorted([boat_a, boat_b]))
    old_state = _pair_collision_state.get(pair_key, "SAFE")
    if new_state != "SAFE" and old_state == "SAFE":
        collisions_predicted += 1
    _pair_collision_state[pair_key] = new_state

    return {
        "executed": True,
        "prediction_a": prediction_a,
        "prediction_b": prediction_b,
        "collision": collision,
    }


def manual_prediction(boat_id: str) -> dict[str, Any]:
    latest = db.latest_telemetry()
    current = next((row for row in latest if row["boat_id"] == boat_id), None)
    if not current:
        return skip_prediction(boat_id, "boat has no telemetry")

    trigger_distance = float("inf")
    trigger_risk = float(current.get("risk", 0.0))
    trigger_ttc: float | None = None
    for other in latest:
        if other["boat_id"] == boat_id:
            continue
        from backend.risk_engine.risk_engine import compute_risk

        result = compute_risk(current, other)
        trigger_distance = min(trigger_distance, result["distance_m"])
        trigger_risk = max(trigger_risk, result["risk"])
        if result["ttc"] is not None:
            trigger_ttc = result["ttc"] if trigger_ttc is None else min(trigger_ttc, result["ttc"])

    if trigger_distance == float("inf"):
        trigger_distance = 999_999.0
    scenario = current.get("scenario", "LIVE")
    return run_prediction_if_needed(boat_id, trigger_distance, trigger_risk, trigger_ttc, scenario)


def metrics() -> dict[str, float | int]:
    return {
        "prediction_skipped": prediction_skipped,
        "prediction_executed": prediction_executed,
        "collisions_predicted": collisions_predicted,
        "avg_prediction_latency_ms": round(mean(_prediction_latencies_ms), 2) if _prediction_latencies_ms else 0,
        "warnings": warnings,
        "recommendations": recommendations,
        "accepted_actions": accepted_actions,
        "avoided_collisions": avoided_collisions,
    }


def track_warning() -> None:
    global warnings
    warnings += 1


def track_recommendation() -> None:
    global recommendations
    recommendations += 1


def track_ack(accepted: bool) -> None:
    global accepted_actions, avoided_collisions
    if accepted:
        accepted_actions += 1
        avoided_collisions += 1
from __future__ import annotations
from typing import Any

from backend.risk_engine.risk_engine import haversine_m
from ml.inference.predict import predict_future_positions

def _state_for_distance(distance_m: float, max_speed_mps: float) -> str:
    # Dynamic radius: At least 20m, or 4 seconds of travel time at the fastest boat's speed
    safety_radius = max(20.0, max_speed_mps * 4.0)
    warning_radius = safety_radius * 1.5

    if distance_m > warning_radius:
        return "SAFE"
    if distance_m >= safety_radius:
        return "WARNING"
    return "DANGER"

def _probability(distance_m: float, max_speed_mps: float) -> float:
    # Scale the probability drop-off based on speed
    horizon = max(50.0, max_speed_mps * 8.0)
    if distance_m >= horizon:
        return 0.0
    return round(max(0.0, min(1.0, 1 - distance_m / horizon)), 3)

def predict_collision(
    trajectory_a: list[dict[str, Any]], 
    trajectory_b: list[dict[str, Any]],
    speed_a: float = 0.0,
    speed_b: float = 0.0
) -> dict[str, float | str]:
    minimum_future_distance = float("inf")
    time_to_collision = 0

    # Calculate the closest they will get over the predicted horizon
    for index, (point_a, point_b) in enumerate(zip(trajectory_a, trajectory_b), start=1):
        distance = haversine_m(point_a["lat"], point_a["lon"], point_b["lat"], point_b["lon"])
        if distance < minimum_future_distance:
            minimum_future_distance = distance
            time_to_collision = index

    if minimum_future_distance == float("inf"):
        return {
            "collision_probability": 0.0,
            "time_to_collision": 0,
            "future_distance": 0,
            "alert_state": "SAFE",
        }

    max_speed = max(speed_a, speed_b)
    state = _state_for_distance(minimum_future_distance, max_speed)
    
    return {
        "collision_probability": _probability(minimum_future_distance, max_speed),
        "time_to_collision": time_to_collision,
        "future_distance": round(minimum_future_distance, 2),
        "alert_state": state,
    }

def predict_collision_from_history(
    history_a: list[dict[str, Any]],
    history_b: list[dict[str, Any]],
) -> dict[str, float | str]:
    # Extract the current speed of both boats right before they are sent to the model
    speed_a = float(history_a[-1].get("speed", 0.0)) if history_a else 0.0
    speed_b = float(history_b[-1].get("speed", 0.0)) if history_b else 0.0

    # Get the next 15 seconds of predictions
    trajectory_a = predict_future_positions(history_a[-10:])
    trajectory_b = predict_future_positions(history_b[-10:])
    
    return predict_collision(trajectory_a, trajectory_b, speed_a, speed_b)
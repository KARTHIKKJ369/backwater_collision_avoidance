from __future__ import annotations

from typing import Any

from backend.risk_engine.risk_engine import haversine_m
from ml.inference.predict import predict_future_positions


def _state_for_distance(distance_m: float) -> str:
    if distance_m > 100:
        return "SAFE"
    if distance_m >= 50:
        return "WARNING"
    return "DANGER"


def _probability(distance_m: float) -> float:
    if distance_m >= 150:
        return 0.0
    return round(max(0.0, min(1.0, 1 - distance_m / 150)), 3)


def predict_collision(trajectory_a: list[dict[str, Any]], trajectory_b: list[dict[str, Any]]) -> dict[str, float | str]:
    minimum_future_distance = float("inf")
    time_to_collision = 0

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

    state = _state_for_distance(minimum_future_distance)
    return {
        "collision_probability": _probability(minimum_future_distance),
        "time_to_collision": time_to_collision,
        "future_distance": round(minimum_future_distance, 2),
        "alert_state": state,
    }


def predict_collision_from_history(
    history_a: list[dict[str, Any]],
    history_b: list[dict[str, Any]],
) -> dict[str, float | str]:
    trajectory_a = predict_future_positions(history_a[-10:])
    trajectory_b = predict_future_positions(history_b[-10:])
    return predict_collision(trajectory_a, trajectory_b)

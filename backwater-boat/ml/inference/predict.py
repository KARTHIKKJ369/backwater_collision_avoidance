from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[1] / "model.h5"


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _trajectory_variance(points: list[dict[str, float]]) -> float:
    if len(points) < 2:
        return 0.0
    origin = points[0]
    lat_scale = 111_320
    lon_scale = 111_320 * math.cos(math.radians(origin["lat"]))
    normalized = [
        [
            ((point["lat"] - origin["lat"]) * lat_scale) / 100,
            ((point["lon"] - origin["lon"]) * lon_scale) / 100,
        ]
        for point in points
    ]
    return float(np.var(np.array(normalized, dtype=np.float32)))


def trajectory_confidence(predicted_points: list[dict[str, float]]) -> float:
    trajectory_variance = _trajectory_variance(predicted_points)
    confidence = _clip(1 - (trajectory_variance * 10), 0.1, 0.99)
    return round(confidence, 3)


def _with_confidence(points: list[dict[str, float]]) -> list[dict[str, float]]:
    results = []
    for index, point in enumerate(points):
        confidence = trajectory_confidence(points[: index + 1])
        results.append({**point, "confidence": confidence})
    return results


def _dead_reckon(history: list[dict[str, Any]], steps: int = 5) -> list[dict[str, float]]:
    if not history:
        return []
    latest = history[-1]
    lat = float(latest["lat"])
    lon = float(latest["lon"])
    speed = float(latest["speed"])
    heading = math.radians(float(latest["heading"]))
    results = []

    for _ in range(steps):
        lat += (speed * math.cos(heading)) / 111_320
        lon += (speed * math.sin(heading)) / (111_320 * math.cos(math.radians(lat)))
        results.append({"lat": round(lat, 7), "lon": round(lon, 7)})
    return _with_confidence(results)


def predict_future_positions(history: list[dict[str, Any]]) -> list[dict[str, float]]:
    if len(history) < 10:
        return _dead_reckon(history)

    try:
        from tensorflow.keras.models import load_model

        model = load_model(MODEL_PATH)
        features = np.array(
            [[point["lat"], point["lon"], point["speed"], point["heading"]] for point in history[-10:]],
            dtype=np.float32,
        ).reshape((1, 10, 4))
        raw = model.predict(features, verbose=0).reshape((5, 2))
        return _with_confidence([{"lat": float(lat), "lon": float(lon)} for lat, lon in raw])
    except Exception:
        return _dead_reckon(history)

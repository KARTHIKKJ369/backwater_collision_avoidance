from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[1] / "model.h5"


def should_trigger_prediction(distance_m: float, risk: float) -> bool:
    return distance_m < 100 or risk > 0.3


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
        results.append({"lat": round(lat, 7), "lon": round(lon, 7), "confidence": 0.55})
    return results


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
        return [{"lat": float(lat), "lon": float(lon), "confidence": 0.85} for lat, lon in raw]
    except Exception:
        return _dead_reckon(history)

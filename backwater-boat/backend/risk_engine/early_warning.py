from __future__ import annotations


def classify_future_distance(future_distance: float) -> str:
    if future_distance > 150:
        return "SAFE"
    if future_distance >= 100:
        return "EARLY_WARNING"
    if future_distance >= 30:
        return "WARNING"
    return "DANGER"

from __future__ import annotations

from typing import Any


def emergency_maneuver(relative_heading: float) -> str:
    if relative_heading >= 150:
        return "HARD_RIGHT"
    if relative_heading > 0:
        return "HARD_LEFT"
    return "STOP"


def recommend_action(relative_heading: float, predicted_path: list[dict[str, Any]], ttc: float) -> str:
    if ttc < 5:
        return emergency_maneuver(relative_heading)
    if not predicted_path:
        return "MAINTAIN"
    if ttc < 10:
        return "SLOW_DOWN"
    if relative_heading >= 150:
        return "TURN_RIGHT"
    if 30 <= relative_heading < 150:
        return "TURN_LEFT"
    return "MAINTAIN"

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    r_lat1 = radians(lat1)
    r_lat2 = radians(lat2)
    a = sin(d_lat / 2) ** 2 + cos(r_lat1) * cos(r_lat2) * sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def heading_difference(h1: float, h2: float) -> float:
    return abs((h1 - h2 + 180) % 360 - 180)


def score_distance(distance_m: float) -> float:
    if distance_m >= 250:
        return 0.0
    return max(0.0, min(1.0, 1 - distance_m / 250))


def score_heading(diff_deg: float) -> float:
    # Crossing and head-on angles deserve more attention than parallel tracks.
    return max(0.0, min(1.0, 1 - abs(90 - min(diff_deg, 180)) / 90))


def score_trajectory(distance_m: float, relative_speed: float, heading_diff: float) -> float:
    closure = min(1.0, max(0.0, relative_speed / 8.0))
    proximity = score_distance(distance_m)
    crossing = score_heading(heading_diff)
    return max(proximity * 0.7 + closure * 0.3, crossing * proximity)


def warning_for_risk(risk: float) -> str:
    if risk < 0.4:
        return "SAFE"
    if risk <= 0.7:
        return "WARNING"
    return "DANGER"


def compute_risk(boat_a: dict[str, Any], boat_b: dict[str, Any]) -> dict[str, Any]:
    distance = haversine_m(boat_a["lat"], boat_a["lon"], boat_b["lat"], boat_b["lon"])
    relative_speed = abs(float(boat_a["speed"]) - float(boat_b["speed"]))
    heading_diff = heading_difference(float(boat_a["heading"]), float(boat_b["heading"]))
    obstacle = max(int(boat_a.get("obstacle", 0)), int(boat_b.get("obstacle", 0)))

    trajectory = score_trajectory(distance, relative_speed, heading_diff)
    distance_score = score_distance(distance)
    heading_score = score_heading(heading_diff)
    risk = (
        0.4 * trajectory
        + 0.3 * distance_score
        + 0.2 * heading_score
        + 0.1 * obstacle
    )
    risk = round(max(0.0, min(1.0, risk)), 3)

    return {
        "risk": risk,
        "warning": warning_for_risk(risk),
        "distance_m": round(distance, 2),
        "relative_speed": round(relative_speed, 2),
        "heading_difference": round(heading_diff, 2),
    }

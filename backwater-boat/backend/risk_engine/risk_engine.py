from __future__ import annotations

from math import asin, atan2, cos, radians, sin, sqrt
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
    if diff_deg >= 150:
        return 1.0
    if 60 <= diff_deg <= 120:
        return 0.8
    return max(0.0, min(1.0, diff_deg / 150))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lon = radians(lon2 - lon1)
    y = sin(d_lon) * cos(radians(lat2))
    x = cos(radians(lat1)) * sin(radians(lat2)) - sin(radians(lat1)) * cos(radians(lat2)) * cos(d_lon)
    return (atan2(y, x) * 180 / 3.141592653589793 + 360) % 360


def closing_speed(boat_a: dict[str, Any], boat_b: dict[str, Any]) -> float:
    bearing_ab = bearing_deg(boat_a["lat"], boat_a["lon"], boat_b["lat"], boat_b["lon"])
    bearing_ba = (bearing_ab + 180) % 360
    speed_a = max(0.0, float(boat_a["speed"]) * cos(radians(float(boat_a["heading"]) - bearing_ab)))
    speed_b = max(0.0, float(boat_b["speed"]) * cos(radians(float(boat_b["heading"]) - bearing_ba)))
    return speed_a + speed_b


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
    relative_speed = closing_speed(boat_a, boat_b)
    heading_diff = heading_difference(float(boat_a["heading"]), float(boat_b["heading"]))
    obstacle = max(int(boat_a.get("obstacle", 0)), int(boat_b.get("obstacle", 0)))

    lstm = score_trajectory(distance, relative_speed, heading_diff)
    distance_score = score_distance(distance)
    heading_score = score_heading(heading_diff)
    ttc = distance / relative_speed if relative_speed > 0 else None
    ttc_score = 1 / (ttc + 1) if ttc is not None else 0.0
    risk = (
        0.5 * lstm
        + 0.2 * distance_score
        + 0.1 * heading_score
        + 0.2 * ttc_score
    )
    risk = max(risk, 0.45) if obstacle and distance < 150 else risk
    risk = round(max(0.0, min(1.0, risk)), 3)

    return {
        "risk": risk,
        "warning": warning_for_risk(risk),
        "distance_m": round(distance, 2),
        "relative_speed": round(relative_speed, 2),
        "heading_difference": round(heading_diff, 2),
        "ttc": round(ttc, 2) if ttc is not None else None,
    }

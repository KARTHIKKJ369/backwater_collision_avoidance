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
    # Head-on (≥150°): maximum risk
    if diff_deg >= 150:
        return 1.0
    # Crossing (60–120°): high risk — vessels on intersecting paths
    if 60 <= diff_deg <= 120:
        return 0.85
    # Overtaking / converging (20–60°): moderate risk
    if 20 <= diff_deg < 60:
        return 0.5
    # Same direction (<20°): low heading risk
    return max(0.0, min(1.0, diff_deg / 20)) * 0.3


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
    return max(proximity * 0.6 + closure * 0.4, crossing * proximity)


def warning_for_risk(risk: float) -> str:
    if risk < 0.4:
        return "SAFE"
    if risk <= 0.6:
        return "WARNING"
    return "DANGER"


def weather_factor(weather: dict[str, Any] | None) -> float:
    """
    Compute a multiplier in [1.0, 1.5] from OpenWeatherMap data.
    Factors considered:
      - visibility_m  : low visibility increases risk
      - wind_speed    : high wind increases manoeuvring difficulty
      - rain / fog    : present/absent flag
    Returns 1.0 (no effect) when weather is None or missing keys.
    """
    if not weather:
        return 1.0

    factor = 1.0

    # Visibility: below 500 m (dense fog) → +0.3; scales linearly up to 5000 m
    visibility = float(weather.get("visibility_m", 10_000))
    if visibility < 5_000:
        factor += 0.3 * max(0.0, (5_000 - visibility) / 5_000)

    # Wind speed: above 10 m/s adds up to +0.15
    wind = float(weather.get("wind_speed", 0))
    if wind > 10:
        factor += min(0.15, (wind - 10) / 20)

    # Precipitation / fog flag from weather condition codes (OpenWeatherMap):
    #   2xx = thunderstorm, 3xx = drizzle, 5xx = rain, 7xx = atmosphere (fog/mist)
    condition_id = int(weather.get("condition_id", 800))
    if condition_id < 700:        # any precipitation
        factor += 0.1
    elif 700 <= condition_id < 800:  # fog / mist / haze
        factor += 0.15

    return round(min(1.5, factor), 3)


def compute_risk(
    boat_a: dict[str, Any],
    boat_b: dict[str, Any],
    weather: dict[str, Any] | None = None,
) -> dict[str, Any]:
    distance = haversine_m(boat_a["lat"], boat_a["lon"], boat_b["lat"], boat_b["lon"])
    relative_speed = closing_speed(boat_a, boat_b)
    heading_diff = heading_difference(float(boat_a["heading"]), float(boat_b["heading"]))
    obstacle = max(int(boat_a.get("obstacle", 0)), int(boat_b.get("obstacle", 0)))

    traj_score = score_trajectory(distance, relative_speed, heading_diff)
    distance_score = score_distance(distance)
    heading_score = score_heading(heading_diff)
    ttc = distance / relative_speed if relative_speed > 0 else None
    ttc_score = 1 / (ttc + 1) if ttc is not None else 0.0

    # Rebalanced weights — heading now 0.20 (was 0.10) so crossing scenarios
    # correctly reach WARNING/DANGER.  TTC kept at 0.20.  Trajectory at 0.40
    # (was 0.50) since it already embeds heading via score_heading().
    risk = (
        0.40 * traj_score
        + 0.20 * distance_score
        + 0.20 * heading_score
        + 0.20 * ttc_score
    )

    # Obstacle proximity boost
    risk = max(risk, 0.45) if obstacle and distance < 150 else risk

    # Weather amplification — scales linearly so fog/rain can push WARNING→DANGER
    w_factor = weather_factor(weather)
    risk = risk * w_factor

    risk = round(max(0.0, min(1.0, risk)), 3)

    return {
        "risk": risk,
        "warning": warning_for_risk(risk),
        "distance_m": round(distance, 2),
        "relative_speed": round(relative_speed, 2),
        "heading_difference": round(heading_diff, 2),
        "ttc": round(ttc, 2) if ttc is not None else None,
        "weather_factor": w_factor,
    }

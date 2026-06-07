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


def overtake_risk(boat_a: dict[str, Any], boat_b: dict[str, Any],
                  distance_m: float, heading_diff: float) -> float:
    """
    Dedicated same-direction overtake / sudden-stop risk term.

    Fires when:
      - Both boats travelling in roughly the same direction (heading_diff < 20°)
      - The following boat (a) is faster than the leading boat (b)
      - They are close enough to matter (distance < 150 m)

    Returns a score in [0, 1] that scales with speed differential and proximity.
    This fills the gap that closing_speed() misses for same-direction pairs,
    because the heading projection makes closing_speed ≈ constant even when
    boat_b is decelerating hard.
    """
    if heading_diff >= 20:
        return 0.0

    speed_a = float(boat_a["speed"])
    speed_b = float(boat_b["speed"])
    delta = speed_a - speed_b          # positive = a closing on b

    if delta <= 0 or distance_m >= 150:
        return 0.0

    # Scale: delta 3 m/s at 50 m → ~0.75 risk
    speed_score   = min(1.0, delta / 6.0)
    proximity_score = max(0.0, 1.0 - distance_m / 150.0)
    return round(speed_score * proximity_score, 3)


def is_diverging(boat_a: dict[str, Any], boat_b: dict[str, Any]) -> bool:
    """
    True when the two boats are moving apart — bearing from a to b is
    more than 90° off each boat's heading, meaning neither is pointing
    toward the other.  Used to suppress false alarms after a crossing
    when boats have already passed.
    """
    bear_ab = bearing_deg(boat_a["lat"], boat_a["lon"],
                          boat_b["lat"], boat_b["lon"])
    bear_ba = (bear_ab + 180) % 360

    # Component of each boat's velocity toward the other
    approach_a = float(boat_a["speed"]) * cos(radians(float(boat_a["heading"]) - bear_ab))
    approach_b = float(boat_b["speed"]) * cos(radians(float(boat_b["heading"]) - bear_ba))

    # Both components negative → both moving away
    return approach_a < 0 and approach_b < 0


def warning_for_risk(risk: float) -> str:
    if risk < 0.45:
        return "SAFE"
    if risk <= 0.65:
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

    visibility = float(weather.get("visibility_m", 10_000))
    if visibility < 5_000:
        factor += 0.3 * max(0.0, (5_000 - visibility) / 5_000)

    wind = float(weather.get("wind_speed", 0))
    if wind > 10:
        factor += min(0.15, (wind - 10) / 20)

    condition_id = int(weather.get("condition_id", 800))
    if condition_id < 700:
        factor += 0.1
    elif 700 <= condition_id < 800:
        factor += 0.15

    return round(min(1.5, factor), 3)


def compute_risk(
    boat_a: dict[str, Any],
    boat_b: dict[str, Any],
    weather: dict[str, Any] | None = None,
) -> dict[str, Any]:
    distance    = haversine_m(boat_a["lat"], boat_a["lon"], boat_b["lat"], boat_b["lon"])
    relative_speed = closing_speed(boat_a, boat_b)
    heading_diff   = heading_difference(float(boat_a["heading"]), float(boat_b["heading"]))
    obstacle = max(int(boat_a.get("obstacle", 0)), int(boat_b.get("obstacle", 0)))

    traj_score     = score_trajectory(distance, relative_speed, heading_diff)
    distance_score = score_distance(distance)
    heading_score  = score_heading(heading_diff)
    ttc = distance / relative_speed if relative_speed > 0 else None
    ttc_score = 1 / (ttc + 1) if ttc is not None else 0.0

    # Same-direction overtake / sudden-stop term
    ot_risk = overtake_risk(boat_a, boat_b, distance, heading_diff)

    # Base risk — overtake_risk replaces some trajectory weight for same-dir pairs
    if ot_risk > 0:
        # Sudden-stop geometry: overtake term gets 0.35, trajectory shrinks to 0.25
        risk = (
            0.25 * traj_score
            + 0.20 * distance_score
            + 0.00 * heading_score   # near-zero for same-direction, skip
            + 0.20 * ttc_score
            + 0.35 * ot_risk
        )
    else:
        risk = (
            0.40 * traj_score
            + 0.20 * distance_score
            + 0.20 * heading_score
            + 0.20 * ttc_score
        )

    # Obstacle proximity boost
    risk = max(risk, 0.45) if obstacle and distance < 150 else risk

    # Sudden-stop imminent collision boost:
    # When a large speed differential exists at close range (ot_risk > 0.5),
    # the overtake term alone doesn't always push risk past DANGER (0.6).
    # Boost to ensure DANGER fires before physical impact.
    if ot_risk > 0.5 and distance < 50:
        risk = max(risk, 0.65)

    # Post-pass suppression — suppress alerts when boats are no longer closing
    # AND there is no overtake/sudden-stop risk (ot_risk near zero).
    # Guarding on ot_risk prevents the suppressor from silencing a genuine
    # sudden-stop event: after B01 overtakes a stopped B02, closing_speed
    # drops to 0 but ot_risk remains high while they are still very close.
    cs = closing_speed(boat_a, boat_b)
    if cs < 0.1 and ot_risk < 0.1:
        risk = min(risk, 0.39)   # push below WARNING threshold (0.4)

    # Weather amplification
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
"""
dataset_generator.py  –  Phase 2: synthetic trajectories with IMU channels
===========================================================================

Adds six IMU-derived columns to every row:

  ax   forward / braking acceleration  (m/s²)   ← Δspeed / Δt
  ay   lateral / centripetal accel.    (m/s²)   ← speed × Δheading_rad / Δt
  az   vertical (heave + gravity)      (m/s²)   ← 9.81 + wave heave, ≈ constant on flat water
  gx   roll rate   (rad/s)             ← wave noise (random, small amplitude)
  gy   pitch rate  (rad/s)             ← wave noise (random, small amplitude)
  gz   yaw rate    (rad/s)             ← Δheading_rad / Δt  (most useful for turns)

Physics rationale
-----------------
ax = Δspeed / Δt
    Sharp negative spike when a boat brakes or cuts throttle.  This is the
    signal that arrives 1-2 seconds before the GPS speed drop becomes obvious,
    making it directly useful for SUDDEN_STOP recall.

ay = speed × |Δheading_rad| / Δt   (signed: + = port, – = starboard)
    Encodes centripetal acceleration during a turn.  Strongly correlated with
    turn sharpness — helps BLIND_TURN detection.

az = 9.81 + heave_noise
    On flat backwater, az ≈ gravity.  Small Gaussian noise models wave heave.
    Provides a sanity-check channel; no discriminative value for classification
    but ensures the IMU tensor looks realistic for the ESP32.

gx, gy  (wave pitch/roll)
    Random Gaussian noise scaled to ±0.05 rad/s — realistic for a small boat
    in calm inland water.  No deterministic signal in synthetic data; on real
    hardware these carry wave-frequency content.

gz = Δheading_rad / Δt
    Yaw rate.  Algebraically identical to the angular velocity the ESP32's
    MPU-6050 z-gyro reads.  Large for BLIND_TURN; near-zero for HEAD_ON and
    CROSSING straight-line legs; short spike at SUDDEN_STOP if the boat yaws
    slightly as it brakes.

Scenario extensions
-------------------
  straight    → cruise at constant speed & heading; all IMU channels near zero.
  crossing    → gentle late heading correction; small gz, ay transient.
  overtaking  → sinusoidal speed oscillation; moderate ax, near-zero gz.
  blind_turn  → sinusoidal heading rate; large gz + ay throughout.
  sudden_stop → linear deceleration from tick 60; large negative ax spike.
                A 3-tick lateral yaw wiggle is added (small gz / ay) to model
                the slight veer a boat makes under hard braking.

Output CSV columns (13 feature cols + 3 metadata):
  scenario, boat_id, time,
  lat, lon, speed, heading,
  ax, ay, az, gx, gy, gz
"""

from __future__ import annotations

import csv
import math
import random
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parents[1] / "datasets"
OUTPUT_PATH = DATASET_DIR / "synthetic_trajectories.csv"

FIELDNAMES = [
    "scenario", "boat_id", "time",
    "lat", "lon", "speed", "heading",
    "ax", "ay", "az", "gx", "gy", "gz",
]

DT = 1.0          # seconds per tick (matches the 1 Hz MQTT publish rate)
G  = 9.81         # m/s²  — gravity constant for az baseline


# ------------------------------------------------------------------
# Kinematics helper
# ------------------------------------------------------------------

def _step(lat: float, lon: float, speed: float, heading: float) -> tuple[float, float]:
    """Advance position by one DT second at given speed & heading."""
    meters = speed * DT
    rad = math.radians(heading)
    d_lat = (meters * math.cos(rad)) / 111_320
    d_lon = (meters * math.sin(rad)) / (111_320 * math.cos(math.radians(lat)))
    return lat + d_lat, lon + d_lon


# ------------------------------------------------------------------
# IMU synthesis helpers
# ------------------------------------------------------------------

def _wave_noise(scale: float = 0.02) -> float:
    """Small Gaussian noise for gx/gy wave channels."""
    return random.gauss(0.0, scale)


def _compute_imu(
    prev_speed: float,
    curr_speed: float,
    prev_heading_deg: float,
    curr_heading_deg: float,
    curr_speed_val: float,
) -> dict[str, float]:
    """
    Derive IMU channels from consecutive kinematic states.

    Parameters
    ----------
    prev_speed, curr_speed   : m/s
    prev_heading_deg, curr_heading_deg : degrees
    curr_speed_val           : current speed (used for ay centripetal term)
    """
    # ax — longitudinal acceleration
    ax = (curr_speed - prev_speed) / DT

    # gz — yaw rate: shortest angular delta in radians / second
    delta_h = curr_heading_deg - prev_heading_deg
    # wrap to (–180, +180]
    delta_h = (delta_h + 180) % 360 - 180
    gz = math.radians(delta_h) / DT

    # ay — lateral (centripetal) acceleration
    ay = curr_speed_val * gz   # v × ω

    # az — heave + gravity
    az = G + _wave_noise(scale=0.05)

    # gx, gy — wave pitch / roll
    gx = _wave_noise(scale=0.02)
    gy = _wave_noise(scale=0.02)

    return {
        "ax": round(ax, 4),
        "ay": round(ay, 4),
        "az": round(az, 4),
        "gx": round(gx, 5),
        "gy": round(gy, 5),
        "gz": round(gz, 4),
    }


# ------------------------------------------------------------------
# Scenario generators
# ------------------------------------------------------------------

def _scenario_straight(points: int) -> list[dict]:
    """Constant speed, constant heading — baseline cruise."""
    heading = random.uniform(30, 60)
    speed   = random.uniform(3.5, 5.5)
    rows = []
    prev_speed, prev_heading = speed, heading

    lat = 9.591 + random.uniform(-0.002, 0.002)
    lon = 76.522 + random.uniform(-0.002, 0.002)

    for t in range(points):
        # Tiny random throttle jitter to make it non-degenerate
        speed += random.gauss(0, 0.01)
        speed = max(2.0, min(7.0, speed))
        lat, lon = _step(lat, lon, speed, heading)
        imu = _compute_imu(prev_speed, speed, prev_heading, heading, speed)
        rows.append({"time": t, "lat": round(lat, 7), "lon": round(lon, 7),
                     "speed": round(speed, 2), "heading": round(heading, 2), **imu})
        prev_speed, prev_heading = speed, heading
    return rows


def _scenario_crossing(points: int) -> list[dict]:
    """
    Boat on crossing course: heading near 90–100°, gentle correction
    in the second half.  Moderate gz / ay transient during correction.
    """
    heading = random.uniform(85, 105)
    speed   = random.uniform(4.0, 5.5)
    rows = []
    prev_speed, prev_heading = speed, heading

    lat = 9.591 + random.uniform(-0.002, 0.002)
    lon = 76.522 + random.uniform(-0.002, 0.002)

    for t in range(points):
        if t > points // 2:
            heading = (heading - 0.15) % 360   # gentle starboard correction
        speed += random.gauss(0, 0.02)
        speed = max(2.0, min(7.0, speed))
        lat, lon = _step(lat, lon, speed, heading)
        imu = _compute_imu(prev_speed, speed, prev_heading, heading, speed)
        rows.append({"time": t, "lat": round(lat, 7), "lon": round(lon, 7),
                     "speed": round(speed, 2), "heading": round(heading, 2), **imu})
        prev_speed, prev_heading = speed, heading
    return rows


def _scenario_overtaking(points: int) -> list[dict]:
    """
    Sinusoidal speed modulation while keeping heading steady.
    ax oscillates; gz and ay near zero (straight line).
    """
    heading = random.uniform(40, 55)
    base_sp = random.uniform(4.5, 6.0)
    rows = []
    prev_speed = base_sp
    prev_heading = heading

    lat = 9.591 + random.uniform(-0.002, 0.002)
    lon = 76.522 + random.uniform(-0.002, 0.002)

    for t in range(points):
        speed = base_sp + 0.8 * math.sin(t / 35)
        lat, lon = _step(lat, lon, speed, heading)
        imu = _compute_imu(prev_speed, speed, prev_heading, heading, speed)
        rows.append({"time": t, "lat": round(lat, 7), "lon": round(lon, 7),
                     "speed": round(speed, 2), "heading": round(heading, 2), **imu})
        prev_speed, prev_heading = speed, heading
    return rows


def _scenario_blind_turn(points: int) -> list[dict]:
    """
    Sinusoidal yaw rate — the key BLIND_TURN signature.
    gz and ay are large and oscillatory.  Speed constant.
    """
    heading = random.uniform(10, 30)
    speed   = random.uniform(2.5, 4.0)
    rows = []
    prev_speed = speed
    prev_heading = heading

    lat = 9.591 + random.uniform(-0.002, 0.002)
    lon = 76.522 + random.uniform(-0.002, 0.002)

    for t in range(points):
        heading = (heading + 0.8 + 8 * math.sin(t / 28)) % 360
        speed += random.gauss(0, 0.02)
        speed = max(1.5, min(5.0, speed))
        lat, lon = _step(lat, lon, speed, heading)
        imu = _compute_imu(prev_speed, speed, prev_heading, heading, speed)
        rows.append({"time": t, "lat": round(lat, 7), "lon": round(lon, 7),
                     "speed": round(speed, 2), "heading": round(heading, 2), **imu})
        prev_speed, prev_heading = speed, heading
    return rows


def _scenario_sudden_stop(points: int) -> list[dict]:
    """
    Normal cruise until tick 60, then sharp deceleration over ~15 ticks.
    ax goes strongly negative; a 3-tick yaw wiggle (gz spike) models
    the slight veer under hard braking.

    This directly targets the SUDDEN_STOP recall deficit (0.231 baseline):
    the ax spike in ticks 60–65 arrives before GPS speed visibly drops.
    """
    heading = random.uniform(70, 90)
    speed   = random.uniform(5.0, 7.0)
    stop_tick = 60
    rows = []
    prev_speed = speed
    prev_heading = heading

    lat = 9.591 + random.uniform(-0.002, 0.002)
    lon = 76.522 + random.uniform(-0.002, 0.002)

    for t in range(points):
        if t >= stop_tick:
            # Decelerate at ~0.6 m/s per tick; clamp at 0
            speed = max(0.0, speed - 0.6)
            # Yaw wiggle for 3 ticks after brake onset — small but real
            if stop_tick <= t < stop_tick + 3:
                heading = (heading + random.gauss(0, 1.5)) % 360

        speed += random.gauss(0, 0.01)
        speed = max(0.0, speed)
        lat, lon = _step(lat, lon, speed, heading)
        imu = _compute_imu(prev_speed, speed, prev_heading, heading, speed)
        rows.append({"time": t, "lat": round(lat, 7), "lon": round(lon, 7),
                     "speed": round(speed, 2), "heading": round(heading, 2), **imu})
        prev_speed, prev_heading = speed, heading
    return rows


# ------------------------------------------------------------------
# Dispatch table
# ------------------------------------------------------------------

_GENERATORS = {
    "straight":    _scenario_straight,
    "crossing":    _scenario_crossing,
    "overtaking":  _scenario_overtaking,
    "blind_turn":  _scenario_blind_turn,
    "sudden_stop": _scenario_sudden_stop,
}


def generate_scenario(
    name: str,
    boat_id: str,
    points: int = 180,
) -> list[dict[str, float | str]]:
    """Generate one trajectory sample and inject metadata columns."""
    if name not in _GENERATORS:
        raise ValueError(f"Unknown scenario '{name}'. "
                         f"Valid: {list(_GENERATORS)}")
    rows = _GENERATORS[name](points)
    for row in rows:
        row["scenario"] = name
        row["boat_id"]  = boat_id
    return rows


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for scenario in _GENERATORS:
        prefix = scenario[:2].upper()
        for sample in range(25):
            rows.extend(
                generate_scenario(scenario, f"{prefix}{sample:02d}")
            )

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows → {OUTPUT_PATH}")
    print(f"Scenarios : {list(_GENERATORS.keys())}")
    print(f"Columns   : {FIELDNAMES}")
    print()
    print("Next steps:")
    print("  1. Update train_lstm.py  — set FEATURE_COLS and INPUT_FEATURES (see below)")
    print("  2. Re-run training       — python ml/training/train_lstm.py")
    print("  3. Update predict.py     — _encode_row() + reshape(1, WINDOW, 11)")
    print("  4. Update norm_params    — add ax/ay/az/gz μ/σ after training")
    print("  5. Update BoatState      — add imu fields; update MQTT publish payload")
    print()
    print("train_lstm.py changes needed:")
    print("  FEATURE_COLS = ('lat','lon','speed','heading','ax','ay','az','gx','gy','gz')")
    print("  INPUT_FEATURES = 11   # lat_n, lon_n, spd_n, sin_h, cos_h, ax_n, ay_n, az_n, gx_n, gy_n, gz_n")


if __name__ == "__main__":
    main()
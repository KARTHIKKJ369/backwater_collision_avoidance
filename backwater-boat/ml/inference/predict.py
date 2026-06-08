from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

MODEL_DIR    = Path(__file__).resolve().parents[1]
TFLITE_PATH  = MODEL_DIR / "model.tflite"
H5_PATH      = MODEL_DIR / "model.h5"
NORM_PATH    = MODEL_DIR / "norm_params.json"

WINDOW_SIZE    = 10
FORECAST_STEPS = 15


# ------------------------------------------------------------------
# Normalisation helpers  (must match train_lstm.py exactly)
# ------------------------------------------------------------------

def _load_norm() -> dict[str, float] | None:
    if NORM_PATH.exists():
        return json.loads(NORM_PATH.read_text())
    return None


def _encode_row(row: dict[str, Any], norm: dict[str, float]) -> list[float]:
    # Kinematic channels (must match train_lstm.py encode_features exactly)
    lat_n = (float(row["lat"])     - norm["lat_mu"]) / norm["lat_sd"]
    lon_n = (float(row["lon"])     - norm["lon_mu"]) / norm["lon_sd"]
    spd_n = float(row["speed"]) / 10.0
    h_rad = math.radians(float(row["heading"]))

    # IMU channels — fall back gracefully if field missing (e.g. dead-reckon history)
    ax_n  = (float(row.get("ax",   0.0)) - norm["ax_mu"]) / norm["ax_sd"]
    ay_n  = (float(row.get("ay",   0.0)) - norm["ay_mu"]) / norm["ay_sd"]
    az_n  = (float(row.get("az",  9.81)) - norm["az_mu"]) / norm["az_sd"]
    gx_n  = (float(row.get("gx",  0.0)) - norm["gx_mu"]) / norm["gx_sd"]
    gy_n  = (float(row.get("gy",  0.0)) - norm["gy_mu"]) / norm["gy_sd"]
    gz_n  = (float(row.get("gz",  0.0)) - norm["gz_mu"]) / norm["gz_sd"]

    return [lat_n, lon_n, spd_n, math.sin(h_rad), math.cos(h_rad),
            ax_n, ay_n, az_n, gx_n, gy_n, gz_n]


def _decode_output(raw: np.ndarray, norm: dict[str, float]) -> list[dict[str, float]]:
    """raw shape: (FORECAST_STEPS, 2) — normalised [lat, lon] pairs."""
    points = []
    for lat_n, lon_n in raw:
        lat = float(lat_n) * norm["lat_sd"] + norm["lat_mu"]
        lon = float(lon_n) * norm["lon_sd"] + norm["lon_mu"]
        points.append({"lat": round(lat, 7), "lon": round(lon, 7)})
    return points


# ------------------------------------------------------------------
# Confidence scoring
# ------------------------------------------------------------------

def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _trajectory_variance(points: list[dict[str, float]]) -> float:
    if len(points) < 2:
        return 0.0
    origin = points[0]
    lat_scale = 111_320
    lon_scale = 111_320 * math.cos(math.radians(origin["lat"]))
    normed = [
        [(p["lat"] - origin["lat"]) * lat_scale / 100,
         (p["lon"] - origin["lon"]) * lon_scale / 100]
        for p in points
    ]
    return float(np.var(np.array(normed, dtype=np.float32)))


def trajectory_confidence(points: list[dict[str, float]]) -> float:
    return round(_clip(1 - _trajectory_variance(points) * 10, 0.1, 0.99), 3)


def _with_confidence(points: list[dict[str, float]]) -> list[dict[str, float]]:
    return [
        {**p, "confidence": trajectory_confidence(points[: i + 1])}
        for i, p in enumerate(points)
    ]


# ------------------------------------------------------------------
# Physical sanity-check constants
# ------------------------------------------------------------------

_DT_SECONDS    = 1.0   # seconds per forecast step — must match simulator cadence
_SANITY_FACTOR = 2.5   # allow up to 2.5× the kinematic maximum displacement
_MIN_FLOOR_M   = 50.0  # minimum allowed radius (metres) for stationary / slow boats


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _sanity_check(points: list[dict[str, float]],
                  origin_lat: float,
                  origin_lon: float,
                  speed_ms: float) -> bool:
    """Return True only when every predicted point sits within the kinematic envelope.

    Root cause addressed:
        The LSTM model outputs normalised absolute lat/lon.  With ``lat_sd ≈ 0.0021``
        a poorly-converged model can emit values only ±5σ from the training mean yet
        decode to positions 1–2 km from the actual boat — while ``_decode_output``
        silently magnifies the error.  This guard catches those out-of-distribution
        outputs *after* decoding and before they reach the risk engine.

    For forecast step *i* (1-indexed) the maximum physically plausible displacement
    from the last known position is::

        max_dist_m = max(speed_ms × i × _DT_SECONDS × _SANITY_FACTOR, _MIN_FLOOR_M)

    The floor ensures the check is not overly aggressive for stationary or very
    slow boats where numerical noise in the model output would otherwise always
    fail at the first step.
    """
    for i, pt in enumerate(points, start=1):
        kinematic_max = speed_ms * i * _DT_SECONDS * _SANITY_FACTOR
        threshold_m   = max(kinematic_max, _MIN_FLOOR_M)
        dist_m = _haversine_m(origin_lat, origin_lon, pt["lat"], pt["lon"])
        if dist_m > threshold_m:
            return False
    return True


# ------------------------------------------------------------------
# Dead-reckoning fallback  (unchanged from original)
# ------------------------------------------------------------------

def _dead_reckon(history: list[dict[str, Any]],
                 steps: int = FORECAST_STEPS) -> list[dict[str, float]]:
    if not history:
        return []
    latest = history[-1]
    lat     = float(latest["lat"])
    lon     = float(latest["lon"])
    speed   = float(latest["speed"])
    heading = math.radians(float(latest["heading"]))
    pts = []
    for _ in range(steps):
        lat += (speed * math.cos(heading)) / 111_320
        lon += (speed * math.sin(heading)) / (111_320 * math.cos(math.radians(lat)))
        pts.append({"lat": round(lat, 7), "lon": round(lon, 7)})
    return _with_confidence(pts)


# ------------------------------------------------------------------
# TFLite inference  (preferred on Pi — no full TF needed)
# ------------------------------------------------------------------

def _predict_tflite(features: np.ndarray,
                    norm: dict[str, float]) -> list[dict[str, float]] | None:
    try:
        # Resolution order for the TFLite interpreter across environments:
        #   tflite-runtime      — lightweight, Python ≤3.9, Pi/container target
        #   ai-edge-litert      — Google's replacement package, Python 3.11+
        #   tensorflow.lite     — full TF install fallback (dev laptop)
        try:
            import tflite_runtime.interpreter as tflite
        except ImportError:
            try:
                import ai_edge_litert.interpreter as tflite
            except ImportError:
                import tensorflow.lite as tflite

        interp = tflite.Interpreter(model_path=str(TFLITE_PATH))
        interp.allocate_tensors()
        inp_idx = interp.get_input_details()[0]["index"]
        out_idx = interp.get_output_details()[0]["index"]
        interp.set_tensor(inp_idx, features)
        interp.invoke()
        raw = interp.get_tensor(out_idx).reshape(FORECAST_STEPS, 2)
        return _with_confidence(_decode_output(raw, norm))
    except Exception as exc:
        print(f"[INFERENCE] tflite failed: {exc}", flush=True)
        return None


# ------------------------------------------------------------------
# Keras / full-TF inference  (dev laptop only)
# ------------------------------------------------------------------

def _predict_keras(features: np.ndarray,
                   norm: dict[str, float]) -> list[dict[str, float]] | None:
    try:
        from tensorflow.keras.models import load_model
        model = load_model(H5_PATH)
        raw = model.predict(features, verbose=0).reshape(FORECAST_STEPS, 2)
        return _with_confidence(_decode_output(raw, norm))
    except Exception:
        return None


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def predict_future_positions(history: list[dict[str, Any]]) -> list[dict[str, float]]:
    """
    Return 5 predicted future positions for the given boat history.

    Resolution order:
      1. TFLite model  (model.tflite)   ← used on Pi / container
      2. Keras model   (model.h5)       ← used on dev laptop
      3. Dead-reckoning fallback        ← used when no model exists yet
    """
    if len(history) < WINDOW_SIZE:
        return _dead_reckon(history)

    norm = _load_norm()
    if norm is None:
        return _dead_reckon(history)

    features = np.array(
        [_encode_row(p, norm) for p in history[-WINDOW_SIZE:]],
        dtype=np.float32,
    ).reshape(1, WINDOW_SIZE, 11)  # 11 features: kin(5) + imu(6)

    # Anchor for the physical sanity check — last observed position / speed.
    latest     = history[-1]
    origin_lat = float(latest["lat"])
    origin_lon = float(latest["lon"])
    speed_ms   = float(latest["speed"])

    # Try TFLite first (fast, Pi-friendly)
    if TFLITE_PATH.exists():
        result = _predict_tflite(features, norm)
        if result:
            if _sanity_check(result, origin_lat, origin_lon, speed_ms):
                print("[INFERENCE] tflite", flush=True)
                return result
            print(
                "[INFERENCE] tflite output failed sanity check "
                f"(speed={speed_ms:.2f} m/s) — falling back to dead-reckoning",
                flush=True,
            )

    # Try Keras (dev machines with full TF installed)
    if H5_PATH.exists():
        result = _predict_keras(features, norm)
        if result:
            if _sanity_check(result, origin_lat, origin_lon, speed_ms):
                print("[INFERENCE] keras", flush=True)
                return result
            print(
                "[INFERENCE] keras output failed sanity check "
                f"(speed={speed_ms:.2f} m/s) — falling back to dead-reckoning",
                flush=True,
            )

    print("[INFERENCE] dead-reckoning (no model loaded)", flush=True)
    return _dead_reckon(history)
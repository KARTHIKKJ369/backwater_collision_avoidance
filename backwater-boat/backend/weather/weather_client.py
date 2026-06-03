"""
Lightweight OpenWeatherMap client for backwater-boat backend.

Fetches current weather for a GPS position and returns a normalised dict
that can be passed directly to risk_engine.compute_risk(weather=...).

Usage
-----
    from backend.weather.weather_client import get_weather_for_position

    w = get_weather_for_position(9.5910, 76.5214)
    # {'visibility_m': 4000, 'wind_speed': 6.2, 'condition_id': 741, ...}

The result is cached per (rounded lat/lon) for CACHE_TTL_SECONDS so every
telemetry tick does not hammer the API.  When the API key is missing or the
request fails the function returns None and the risk engine applies no
weather penalty.
"""

from __future__ import annotations

import json as _json
import os
import time
import urllib.request
from typing import Any

OWM_API_KEY: str | None = os.getenv("OPENWEATHER_API_KEY")
CACHE_TTL_SECONDS = 300  # refresh every 5 minutes
_cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}


def _round_coord(value: float, decimals: int = 2) -> float:
    return round(value, decimals)


def _fetch_owm(lat: float, lon: float) -> dict[str, Any] | None:
    if not OWM_API_KEY:
        return None
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric"
    )
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        weather_id = data.get("weather", [{}])[0].get("id", 800)
        wind_speed = data.get("wind", {}).get("speed", 0.0)
        # OWM visibility is in metres, max reported is 10 000
        visibility = data.get("visibility", 10_000)
        return {
            "condition_id": weather_id,
            "wind_speed": float(wind_speed),
            "visibility_m": float(visibility),
            "description": data.get("weather", [{}])[0].get("description", ""),
            "temp_c": data.get("main", {}).get("temp"),
        }
    except Exception as exc:
        print(f"[weather] OWM fetch failed: {exc}", flush=True)
        return None


def get_weather_for_position(lat: float, lon: float) -> dict[str, Any] | None:
    """Return weather dict or None (caller treats None as no weather penalty)."""
    key = (_round_coord(lat), _round_coord(lon))
    cached_at, cached_data = _cache.get(key, (0.0, {}))
    if time.time() - cached_at < CACHE_TTL_SECONDS and cached_data:
        return cached_data

    data = _fetch_owm(lat, lon)
    if data:
        _cache[key] = (time.time(), data)
    return data


def mock_weather(preset: str) -> dict[str, Any]:
    """
    Return a deterministic mock weather dict for offline / CI testing.
    Used when OPENWEATHER_API_KEY is not set.
    """
    presets: dict[str, dict[str, Any]] = {
        "FOG":   {"condition_id": 741, "wind_speed": 2.0,  "visibility_m": 300,   "description": "fog"},
        "RAIN":  {"condition_id": 501, "wind_speed": 8.0,  "visibility_m": 3000,  "description": "moderate rain"},
        "STORM": {"condition_id": 211, "wind_speed": 18.0, "visibility_m": 1500,  "description": "thunderstorm"},
        "CLEAR": {"condition_id": 800, "wind_speed": 1.5,  "visibility_m": 10000, "description": "clear sky"},
    }
    return presets.get(preset.upper(), presets["CLEAR"])

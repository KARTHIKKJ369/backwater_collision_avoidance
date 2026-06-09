"""
cycle_sim.py — cycles through all 4 scenarios for live demo.

Each scenario runs for SCENARIO_TICKS ticks, then resets to the next one.
Publishes boat positions to MQTT exactly like boat_sim.py so the backend
sees no difference.
"""
from __future__ import annotations

import json
import math
import os
import time

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

SCENARIO_TICKS = 60      # ticks before switching scenario
TICK_INTERVAL  = 1.0     # seconds per tick

SCENARIOS = ["HEAD_ON", "CROSSING", "BLIND_TURN", "SUDDEN_STOP"]


# ── Scenario initial states ───────────────────────────────────────────────────

def _init_states(scenario: str) -> list[dict]:
    if scenario == "HEAD_ON":
        return [
            {"boat_id": "B01", "lat": 9.5910, "lon": 76.5211, "speed": 8.0, "heading": 90,  "obstacle": 0},
            {"boat_id": "B02", "lat": 9.5910, "lon": 76.5240, "speed": 8.0, "heading": 270, "obstacle": 0},
        ]
    if scenario == "CROSSING":
        return [
            {"boat_id": "B01", "lat": 9.5910, "lon": 76.5214, "speed": 4.6, "heading": 85,  "obstacle": 0},
            {"boat_id": "B02", "lat": 9.5904, "lon": 76.5228, "speed": 4.4, "heading": 350, "obstacle": 0},
        ]
    if scenario == "BLIND_TURN":
        return [
            {"boat_id": "B01", "lat": 9.5907, "lon": 76.5211, "speed": 3.8, "heading": 30,  "obstacle": 1},
            {"boat_id": "B02", "lat": 9.5919, "lon": 76.5220, "speed": 3.5, "heading": 215, "obstacle": 1},
        ]
    if scenario == "SUDDEN_STOP":
        return [
            {"boat_id": "B01", "lat": 9.5910, "lon": 76.5216, "speed": 6.0, "heading": 80,  "obstacle": 0},
            {"boat_id": "B02", "lat": 9.5911, "lon": 76.5220, "speed": 5.8, "heading": 80,  "obstacle": 0},
        ]
    raise ValueError(f"Unknown scenario: {scenario}")


# ── Per-tick scenario update ──────────────────────────────────────────────────

def _update(states: list[dict], scenario: str, tick: int) -> None:
    if scenario == "CROSSING":
        if tick > 30:
            states[1]["heading"] -= 0.4
    elif scenario == "BLIND_TURN":
        states[0]["heading"] += 1.4
        states[1]["heading"] -= 1.2
    elif scenario == "SUDDEN_STOP":
        if tick > 15:
            states[1]["speed"] = max(0.0, states[1]["speed"] - 0.8)
    # HEAD_ON: no update needed


# ── Physics step ─────────────────────────────────────────────────────────────

def _step(b: dict) -> None:
    rad = math.radians(b["heading"])
    b["lat"] += (b["speed"] * math.cos(rad)) / 111_320
    b["lon"] += (b["speed"] * math.sin(rad)) / (111_320 * math.cos(math.radians(b["lat"])))


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="boat-simulator")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    scenario_idx = 0

    while True:
        scenario = SCENARIOS[scenario_idx % len(SCENARIOS)]
        states   = _init_states(scenario)

        print(f"[SIM] Starting scenario: {scenario}", flush=True)

        next_tick = time.monotonic()

        for tick in range(SCENARIO_TICKS):
            _update(states, scenario, tick)

            for b in states:
                _step(b)
                payload = {
                    "boat_id":   b["boat_id"],
                    "timestamp": time.time(),   # real Unix time — was: tick (integer)
                    "lat":       round(b["lat"],  7),
                    "lon":       round(b["lon"],  7),
                    "speed":     round(b["speed"], 2),
                    "heading":   round(b["heading"] % 360, 2),
                    "obstacle":  b["obstacle"],
                    "scenario":  scenario,
                }
                client.publish(f"boats/{b['boat_id']}/sensor", json.dumps(payload))
                print(json.dumps(payload), flush=True)

            next_tick += TICK_INTERVAL
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)

        print(f"[SIM] Scenario {scenario} done, switching...", flush=True)
        scenario_idx += 1


if __name__ == "__main__":
    main()
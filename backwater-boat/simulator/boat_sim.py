from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


@dataclass
class BoatState:
    boat_id: str
    lat: float
    lon: float
    speed: float
    heading: float
    obstacle: int = 0

    def step(self) -> None:
        rad = math.radians(self.heading)
        self.lat += (self.speed * math.cos(rad)) / 111_320
        self.lon += (self.speed * math.sin(rad)) / (111_320 * math.cos(math.radians(self.lat)))

    def payload(self, timestamp: int) -> dict[str, float | int | str]:
        return {
            "boat_id": self.boat_id,
            "timestamp": timestamp,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "speed": round(self.speed, 2),
            "heading": round(self.heading % 360, 2),
            "obstacle": self.obstacle,
        }


def make_boats(scenario: str) -> list[BoatState]:
    module_name = scenario.lower()
    if module_name == "head_on":
        module_name = "head_on"
    if module_name in {"head_on", "crossing", "blind_turn", "sudden_stop"}:
        module = importlib.import_module(f"scenarios.{module_name}")
        return [BoatState(**state) for state in module.make_states()]

    if scenario == "straight":
        return [
            BoatState("B01", 9.5910, 76.5220, 4.2, 65),
            BoatState("B02", 9.5898, 76.5208, 3.8, 65),
        ]
    if scenario == "collision":
        return [
            BoatState("B01", 9.5910, 76.5211, 5.0, 90),
            BoatState("B02", 9.5910, 76.5240, 5.0, 270),
        ]
    raise ValueError(f"Unknown scenario: {scenario}")


def update_scenario(boats: list[BoatState], scenario: str, tick: int) -> None:
    module_name = scenario.lower()
    if module_name in {"head_on", "crossing", "blind_turn", "sudden_stop"}:
        module = importlib.import_module(f"scenarios.{module_name}")
        module.update(boats, tick)
    elif scenario == "collision":
        for boat in boats:
            boat.speed = max(2.8, boat.speed - 0.005 * tick)


def connect_client() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="boat-simulator")
    for attempt in range(20):
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            return client
        except OSError:
            time.sleep(min(5, attempt + 1))
    raise RuntimeError(f"Unable to connect to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backwater boat MQTT simulator")
    parser.add_argument(
        "--scenario",
        choices=["straight", "crossing", "blind_turn", "collision", "HEAD_ON", "head_on", "sudden_stop"],
        default="crossing",
    )
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    client = connect_client()
    scenario = "head_on" if args.scenario == "HEAD_ON" else args.scenario
    boats = make_boats(scenario)
    tick = 0
    print(f"Publishing {args.scenario} scenario to {MQTT_HOST}:{MQTT_PORT}", flush=True)

    while True:
        update_scenario(boats, scenario, tick)
        for boat in boats:
            boat.step()
            payload = boat.payload(tick)
            topic = f"boats/{boat.boat_id}/sensor"
            client.publish(topic, json.dumps(payload), qos=0)
            print(json.dumps(payload), flush=True)
        tick += 1
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

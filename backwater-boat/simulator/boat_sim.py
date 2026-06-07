from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import random
import threading
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

TOPIC_RECOMMENDATION = "boats/+/recommendation"


@dataclass
class BoatState:
    boat_id: str
    lat: float
    lon: float
    speed: float
    heading: float
    obstacle: int = 0

    base_speed: float | None = None
    base_heading: float | None = None

    active_action: str | None = None
    action_until: int = 0

    # IMU channels — derived each tick in step()
    ax: float = 0.0   # forward accel   (m/s²)
    ay: float = 0.0   # lateral accel   (m/s²)
    az: float = 9.81  # vertical + heave (m/s²)
    gx: float = 0.0   # roll rate       (rad/s)
    gy: float = 0.0   # pitch rate      (rad/s)
    gz: float = 0.0   # yaw rate        (rad/s)

    # Previous-tick kinematics needed to derive IMU deltas
    _prev_speed: float = 0.0
    _prev_heading: float = 0.0

    def __post_init__(self):
        self.base_speed = self.speed
        self.base_heading = self.heading
        self._prev_speed = self.speed
        self._prev_heading = self.heading

    def step(self) -> None:
        # --- Derive IMU channels from kinematic delta (DT = 1 s) ---
        self.ax = round(self.speed - self._prev_speed, 4)

        delta_h = (self.heading - self._prev_heading + 180) % 360 - 180
        self.gz = round(math.radians(delta_h), 4)          # yaw rate rad/s
        self.ay = round(self.speed * self.gz, 4)           # centripetal m/s²
        self.az = round(9.81 + random.gauss(0, 0.05), 4)  # gravity + heave
        self.gx = round(random.gauss(0, 0.02), 5)         # wave roll
        self.gy = round(random.gauss(0, 0.02), 5)         # wave pitch

        self._prev_speed   = self.speed
        self._prev_heading = self.heading

        # --- Advance position ---
        rad = math.radians(self.heading)

        self.lat += (
            self.speed * math.cos(rad)
        ) / 111_320

        self.lon += (
            self.speed * math.sin(rad)
        ) / (
            111_320
            * math.cos(
                math.radians(self.lat)
            )
        )

    def recover(self, tick: int) -> None:

        if (
            self.active_action
            and tick >= self.action_until
        ):

            print(
                f"[SIM] restoring {self.boat_id}",
                flush=True,
            )

            self.speed = self.base_speed
            self.heading = self.base_heading

            self.active_action = None

    def apply_recommendation(
        self,
        action: str,
        tick: int,
    ) -> bool:

        if (
            self.active_action == action
            and tick < self.action_until
        ):
            return False

        self.active_action = action

        self.action_until = tick + 5

        print(
            f"[SIM] applying {self.boat_id}: {action}",
            flush=True,
        )

        if action == "TURN_RIGHT":
            self.heading += 15

        elif action == "TURN_LEFT":
            self.heading -= 15

        elif action == "HARD_RIGHT":
            self.heading += 30

        elif action == "HARD_LEFT":
            self.heading -= 30

        elif action == "SLOW_DOWN":
            self.speed *= 0.8

        elif action == "STOP":
            self.speed = 0.0

        print(
            f"[SIM] "
            f"speed={self.speed:.2f} "
            f"heading={self.heading:.2f}",
            flush=True,
        )

        return True

    def payload(
        self,
        timestamp,
    ):

        return {
            "boat_id": self.boat_id,
            "timestamp": timestamp,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "speed": round(self.speed, 2),
            "heading": round(self.heading % 360, 2),
            "obstacle": self.obstacle,
            # IMU channels — derived from kinematics in step()
            "ax": self.ax,
            "ay": self.ay,
            "az": self.az,
            "gx": self.gx,
            "gy": self.gy,
            "gz": self.gz,
        }


def make_boats(scenario):

    module = importlib.import_module(
        f"scenarios.{scenario.lower()}"
    )

    return [
        BoatState(**x)
        for x in module.make_states()
    ]


def update_scenario(
    boats,
    scenario,
    tick,
):

    module = importlib.import_module(
        f"scenarios.{scenario.lower()}"
    )

    active = []

    for boat in boats:

        if boat.active_action:
            continue

        active.append(boat)

    module.update(
        active,
        tick,
    )


def connect_client():

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="boat-simulator",
    )

    client.connect(
        MQTT_HOST,
        MQTT_PORT,
        keepalive=60,
    )

    client.loop_start()

    return client


def topic_boat(topic):

    parts = topic.split("/")

    if len(parts) >= 3:

        return parts[1]

    return None


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--scenario",
        default="HEAD_ON",
    )

    parser.add_argument(
        "--interval",
        default=1.0,
        type=float,
    )

    args = parser.parse_args()

    scenario = args.scenario.lower()

    boats = make_boats(
        scenario
    )

    boats_by_id = {
        b.boat_id: b
        for b in boats
    }

    pending = {}

    lock = threading.Lock()

    client = connect_client()

    def on_connect(
        c,
        u,
        f,
        rc,
        p,
    ):

        c.subscribe(
            TOPIC_RECOMMENDATION
        )

    def on_message(
        c,
        u,
        msg,
    ):

        try:

            payload = json.loads(
                msg.payload.decode()
            )

        except Exception:

            return

        action = (
            str(
                payload.get(
                    "action",
                    "",
                )
            )
            .strip()
            .upper()
        )

        if (
            not action
            or action == "MAINTAIN"
        ):
            return

        boat = (
            payload.get(
                "boat_id"
            )
            or topic_boat(
                msg.topic
            )
        )

        if not boat:
            return

        print(
            f"[SIM] received {boat} -> {action}",
            flush=True,
        )

        with lock:

            pending[
                boat
            ] = action

        client.publish(
            f"boats/{boat}/ack",
            json.dumps(
                {
                    "boat_id": boat,
                    "action": action,
                    "accepted": True,
                }
            ),
        )

    client.on_connect = on_connect

    client.on_message = on_message

    client.subscribe(
        TOPIC_RECOMMENDATION
    )

    tick = 0

    print(
        f"Publishing {args.scenario}",
        flush=True,
    )

    while True:

        for boat in boats:

            boat.recover(
                tick
            )

        update_scenario(
            boats,
            scenario,
            tick,
        )

        with lock:

            for boat in boats:

                action = pending.pop(
                    boat.boat_id,
                    None,
                )

                if action:

                    boat.apply_recommendation(
                        action,
                        tick,
                    )

        for boat in boats:

            boat.step()

            payload = boat.payload(
                tick
            )

            payload[
                "scenario"
            ] = (
                args.scenario
                .upper()
            )

            client.publish(
                f"boats/{boat.boat_id}/sensor",
                json.dumps(
                    payload
                ),
            )

            print(
                json.dumps(
                    payload
                ),
                flush=True,
            )

        tick += 1

        time.sleep(
            args.interval
        )


if __name__ == "__main__":
    main()
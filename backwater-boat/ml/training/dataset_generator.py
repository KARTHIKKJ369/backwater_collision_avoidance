from __future__ import annotations

import csv
import math
import random
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parents[1] / "datasets"
OUTPUT_PATH = DATASET_DIR / "synthetic_trajectories.csv"


def _step(lat: float, lon: float, speed: float, heading: float) -> tuple[float, float]:
    meters = speed
    rad = math.radians(heading)
    d_lat = (meters * math.cos(rad)) / 111_320
    d_lon = (meters * math.sin(rad)) / (111_320 * math.cos(math.radians(lat)))
    return lat + d_lat, lon + d_lon


def generate_scenario(name: str, boat_id: str, points: int = 180) -> list[dict[str, float | str]]:
    lat = 9.591 + random.uniform(-0.002, 0.002)
    lon = 76.522 + random.uniform(-0.002, 0.002)
    heading = {"straight": 45, "crossing": 95, "overtaking": 50, "blind_turn": 20}[name]
    speed = {"straight": 4.2, "crossing": 4.8, "overtaking": 5.4, "blind_turn": 3.2}[name]
    rows: list[dict[str, float | str]] = []

    for t in range(points):
        if name == "blind_turn":
            heading = (heading + 0.8 + 8 * math.sin(t / 28)) % 360
        elif name == "crossing" and t > points // 2:
            heading = (heading - 0.15) % 360
        elif name == "overtaking":
            speed = 5.0 + 0.8 * math.sin(t / 35)

        lat, lon = _step(lat, lon, speed, heading)
        rows.append(
            {
                "scenario": name,
                "boat_id": boat_id,
                "time": t,
                "lat": round(lat, 7),
                "lon": round(lon, 7),
                "speed": round(speed, 2),
                "heading": round(heading, 2),
            }
        )
    return rows


def main() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, float | str]] = []
    for scenario in ("straight", "crossing", "overtaking", "blind_turn"):
        for sample in range(25):
            rows.extend(generate_scenario(scenario, f"{scenario[:2].upper()}{sample:02d}"))

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["scenario", "boat_id", "time", "lat", "lon", "speed", "heading"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

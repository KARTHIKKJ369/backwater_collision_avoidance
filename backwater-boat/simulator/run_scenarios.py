from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.request
from pathlib import Path

from boat_sim import connect_client, make_boats, update_scenario

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
CSV_PATH = RESULTS_DIR / "evaluation.csv"
SUMMARY_PATH = RESULTS_DIR / "summary.json"
SCENARIOS = ["HEAD_ON", "CROSSING", "BLIND_TURN", "SUDDEN_STOP"]


def _get_json(path: str) -> dict[str, float | int | str]:
    with urllib.request.urlopen(f"{API_BASE}{path}", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _scenario_key(name: str) -> str:
    return name.lower()


def run_scenario(name: str, duration: int, interval: float) -> dict[str, float | int | str]:
    scenario = _scenario_key(name)
    client = connect_client()
    boats = make_boats(scenario)

    try:
        for tick in range(duration):
            update_scenario(boats, scenario, tick)
            for boat in boats:
                boat.step()
                payload = boat.payload(time.time())  # real Unix time — was: tick (integer)
                payload["scenario"] = name
                client.publish(f"boats/{boat.boat_id}/sensor", json.dumps(payload), qos=0)
            time.sleep(interval)

        time.sleep(2)
        evaluation = _get_json(f"/evaluation?scenario={name}")
        metrics = _get_json("/metrics")
        timeline = _get_json(f"/timeline?scenario={name}")
        write_timeline(name, timeline if isinstance(timeline, list) else [])
        return {
            "scenario": name,
            "alerts": metrics.get("alerts_total", 0),
            "predictions": metrics.get("predictions_total", 0),
            "collisions": metrics.get("collisions_predicted", 0),
            "avg_risk": metrics.get("avg_risk", 0),
            "latency": metrics.get("avg_prediction_latency_ms", 0),
            "precision": evaluation.get("precision", 0),
        }
    finally:
        # Always disconnect cleanly so the old client's loop_start() background
        # thread doesn't auto-reconnect and fight with the next scenario's client.
        client.loop_stop()
        client.disconnect()


def write_results(rows: list[dict[str, float | int | str]]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    columns = ["scenario", "alerts", "predictions", "collisions", "avg_risk", "latency", "precision"]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "scenarios": len(rows),
        "alerts": rows[-1]["alerts"] if rows else 0,
        "predictions": rows[-1]["predictions"] if rows else 0,
        "collisions": rows[-1]["collisions"] if rows else 0,
        "avg_risk": rows[-1]["avg_risk"] if rows else 0,
        "latency": rows[-1]["latency"] if rows else 0,
        "precision": rows[-1]["precision"] if rows else 0,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def write_timeline(name: str, rows: list[dict[str, float | int | str]]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name.lower()}.csv"
    columns = ["timestamp", "distance", "future_distance", "risk", "ttc", "prediction", "alert"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "timestamp": row.get("t", 0),
                    "distance": row.get("distance", 0),
                    "future_distance": row.get("future_distance", 0),
                    "risk": row.get("risk", 0),
                    "ttc": row.get("ttc", 0),
                    "prediction": row.get("prediction", 0),
                    "alert": row.get("alert", ""),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run automated evaluation scenarios")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--interval", type=float, default=0.25)
    args = parser.parse_args()

    rows = [run_scenario(name, args.duration, args.interval) for name in SCENARIOS]
    write_results(rows)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
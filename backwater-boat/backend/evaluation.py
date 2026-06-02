from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any

from backend.database import db
from backend.predict_controller import metrics as prediction_metrics
from backend.risk_engine.risk_engine import compute_risk, haversine_m

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
CSV_PATH = RESULTS_DIR / "evaluation.csv"
SUMMARY_PATH = RESULTS_DIR / "summary.json"


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0


def _avg_ttc() -> float:
    latest = db.latest_telemetry()
    values = []
    for index, boat_a in enumerate(latest):
        for boat_b in latest[index + 1 :]:
            values.append(compute_risk(boat_a, boat_b)["ttc"])
    finite = [value for value in values if value < 999_999]
    return round(mean(finite), 2) if finite else 0.0


def _avg_prediction_error(predictions: list[dict[str, Any]]) -> float:
    errors = []
    for prediction in predictions:
        future = db.telemetry_after(prediction["boat_id"], prediction["timestamp"], limit=1)
        if not future:
            continue
        actual = future[0]
        errors.append(haversine_m(prediction["pred_lat"], prediction["pred_lon"], actual["lat"], actual["lon"]))
    return round(mean(errors), 2) if errors else 0.0


def _rows(table: str, scenario: str) -> list[dict[str, Any]]:
    db.init_db()
    if scenario == "LIVE":
        return db.fetch_all(table, 10_000)
    return db.fetch_by_scenario(table, scenario, 10_000)


def _prediction_future_distance(predictions: list[dict[str, Any]]) -> float:
    by_boat: dict[str, list[dict[str, Any]]] = {}
    for prediction in reversed(predictions):
        by_boat.setdefault(prediction["boat_id"], []).append(prediction)
    boat_ids = sorted(by_boat)
    if len(boat_ids) < 2:
        return 0.0

    distances = []
    for point_a, point_b in zip(by_boat[boat_ids[0]][:5], by_boat[boat_ids[1]][:5]):
        distances.append(haversine_m(point_a["pred_lat"], point_a["pred_lon"], point_b["pred_lat"], point_b["pred_lon"]))
    return round(min(distances), 2) if distances else 0.0


def timeline(scenario: str = "LIVE") -> list[dict[str, float | int | str]]:
    scenario = scenario.upper()
    telemetry = list(reversed(_rows("telemetry", scenario)))
    predictions = _rows("prediction", scenario)
    alerts = _rows("alerts", scenario)
    future_distance = _prediction_future_distance(predictions)
    alert_by_time = {round(float(alert["timestamp"]), 3): alert["severity"] for alert in alerts}

    by_time: dict[float, list[dict[str, Any]]] = {}
    for row in telemetry:
        by_time.setdefault(float(row["timestamp"]), []).append(row)

    rows: list[dict[str, float | int | str]] = []
    for timestamp, samples in sorted(by_time.items()):
        if len(samples) < 2:
            continue
        risk = compute_risk(samples[0], samples[1])
        rows.append(
            {
                "t": timestamp,
                "distance": risk["distance_m"],
                "future_distance": future_distance,
                "risk": max(float(sample["risk"]) for sample in samples),
                "ttc": risk["ttc"],
                "prediction": 1 if predictions else 0,
                "alert": alert_by_time.get(round(timestamp, 3), ""),
            }
        )
    return rows


def evaluate(scenario: str = "LIVE") -> dict[str, float | int | str]:
    scenario = scenario.upper()
    alerts = _rows("alerts", scenario)
    predictions = _rows("prediction", scenario)
    telemetry = _rows("telemetry", scenario)
    prediction = prediction_metrics()

    collision_alerts = [alert for alert in alerts if alert["severity"] == "DANGER"]
    warning_alerts = [alert for alert in alerts if alert["severity"] == "WARNING"]
    high_risk_samples = [row for row in telemetry if row["risk"] >= 0.5]
    collisions = prediction["collisions_predicted"]
    precision = _safe_div(len(collision_alerts), max(len(alerts), collisions))
    recall = _safe_div(len(collision_alerts), len(high_risk_samples))
    f1 = _safe_div(2 * precision * recall, precision + recall)
    timeline_rows = timeline(scenario)
    ttc_values = [float(row["ttc"]) for row in timeline_rows if float(row["ttc"]) < 999_999]

    result = {
        "scenario": scenario,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_alarm_rate": _safe_div(len(warning_alerts), len(alerts)),
        "avg_ttc": round(mean(ttc_values), 2) if ttc_values else _avg_ttc(),
        "avg_prediction_error": _avg_prediction_error(predictions),
        "alerts": len(alerts),
        "predictions": len(predictions),
        "collisions": collisions,
        "avg_risk": db.average_risk(None if scenario == "LIVE" else scenario),
        "latency": prediction["avg_prediction_latency_ms"],
    }
    export_results([result], scenario)
    return result


def export_results(rows: list[dict[str, Any]], scenario: str = "LIVE") -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    columns = ["scenario", "alerts", "predictions", "collisions", "avg_risk", "latency", "precision"]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, 0) for column in columns})

    timeline_rows = timeline(scenario)
    timeline_path = RESULTS_DIR / f"{scenario.lower()}.csv"
    timeline_columns = ["timestamp", "distance", "future_distance", "risk", "ttc", "prediction", "alert"]
    with timeline_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=timeline_columns)
        writer.writeheader()
        for row in timeline_rows:
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

    summary = rows[-1] if rows else {}
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

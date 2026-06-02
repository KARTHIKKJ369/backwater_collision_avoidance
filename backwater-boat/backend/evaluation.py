from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any

from backend.database import db
from backend.predict_controller import metrics as prediction_metrics
from backend.risk_engine.predictive_collision import predict_collision
from backend.risk_engine.risk_engine import compute_risk, haversine_m
from ml.inference.predict import predict_future_positions

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
            ttc = compute_risk(boat_a, boat_b)["ttc"]
            if ttc is not None:
                values.append(ttc)
    return round(mean(values), 2) if values else 0.0


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


def timeline(scenario: str = "LIVE") -> list[dict[str, float | int | str | None]]:
    scenario = scenario.upper()
    telemetry = list(reversed(_rows("telemetry", scenario)))
    alerts = _rows("alerts", scenario)
    alert_by_time = {round(float(alert["timestamp"]), 3): alert["severity"] for alert in alerts}

    by_time: dict[float, list[dict[str, Any]]] = {}
    by_boat: dict[str, list[dict[str, Any]]] = {}
    for row in telemetry:
        by_time.setdefault(float(row["timestamp"]), []).append(row)
        by_boat.setdefault(row["boat_id"], []).append(row)

    histories: dict[str, list[dict[str, Any]]] = {}
    prediction_cache: dict[
        tuple[str, str, tuple[float, ...], tuple[float, ...]],
        dict[str, float | str],
    ] = {}
    trajectory_cache: dict[tuple[str, tuple[float, ...]], list[dict[str, float]]] = {}
    indices: dict[str, int] = {}
    window = 10

    rows: list[dict[str, float | int | str | None]] = []
    for timestamp, samples in sorted(by_time.items()):
        if len(samples) < 2:
            continue
        for sample in samples:
            history = histories.setdefault(sample["boat_id"], [])
            history.append(sample)
            if len(history) > window:
                history.pop(0)
            indices[sample["boat_id"]] = indices.get(sample["boat_id"], -1) + 1
        boat_ids = sorted(histories)
        future_distance = 0.0
        prediction_error = None
        if len(boat_ids) >= 2:
            history_a = histories[boat_ids[0]]
            history_b = histories[boat_ids[1]]
            if len(history_a) >= window and len(history_b) >= window:
                key_a = tuple(point["timestamp"] for point in history_a[-3:])
                key_b = tuple(point["timestamp"] for point in history_b[-3:])
                traj_key_a = (boat_ids[0], key_a)
                traj_key_b = (boat_ids[1], key_b)
                if traj_key_a not in trajectory_cache:
                    trajectory_cache[traj_key_a] = predict_future_positions(history_a)
                if traj_key_b not in trajectory_cache:
                    trajectory_cache[traj_key_b] = predict_future_positions(history_b)
                cache_key = (boat_ids[0], boat_ids[1], key_a, key_b)
                if cache_key not in prediction_cache:
                    prediction_cache[cache_key] = predict_collision(
                        trajectory_cache[traj_key_a],
                        trajectory_cache[traj_key_b],
                    )
                collision = prediction_cache[cache_key]
                future_distance = collision["future_distance"]

                error_values = []
                for boat_id, traj_key in ((boat_ids[0], traj_key_a), (boat_ids[1], traj_key_b)):
                    predicted = trajectory_cache[traj_key]
                    current_index = indices.get(boat_id, -1)
                    actual = by_boat.get(boat_id, [])
                    if current_index >= 0 and actual:
                        future_actual = actual[current_index + 1 : current_index + 1 + len(predicted)]
                        for pred_point, actual_point in zip(predicted, future_actual):
                            error_values.append(
                                haversine_m(
                                    pred_point["lat"],
                                    pred_point["lon"],
                                    actual_point["lat"],
                                    actual_point["lon"],
                                )
                            )
                if error_values:
                    prediction_error = round(mean(error_values), 2)
        risk = compute_risk(samples[0], samples[1])
        rows.append(
            {
                "t": timestamp,
                "distance": risk["distance_m"],
                "future_distance": future_distance,
                "risk": max(float(sample["risk"]) for sample in samples),
                "ttc": risk["ttc"],
                "prediction_error": prediction_error,
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
    ttc_values = [row["ttc"] for row in timeline_rows if row.get("ttc") is not None]
    prediction_errors = [
        float(row["prediction_error"])
        for row in timeline_rows
        if row.get("prediction_error") is not None
    ]

    result = {
        "scenario": scenario,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_alarm_rate": _safe_div(len(warning_alerts), len(alerts)),
        "avg_ttc": round(mean(ttc_values), 2) if ttc_values else _avg_ttc(),
        "avg_prediction_error": round(mean(prediction_errors), 2) if prediction_errors else 0.0,
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
    timeline_columns = ["timestamp", "distance", "future_distance", "risk", "ttc", "prediction_error", "alert"]
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
                    "ttc": row["ttc"] if row.get("ttc") is not None else "N/A",
                    "prediction_error": row.get("prediction_error", 0) or 0,
                    "alert": row.get("alert", ""),
                }
            )

    summary = rows[-1] if rows else {}
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

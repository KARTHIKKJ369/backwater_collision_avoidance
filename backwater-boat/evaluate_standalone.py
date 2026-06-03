"""
Standalone evaluation — no MQTT broker or FastAPI required.
Directly simulates all 4 scenarios, runs risk engine + LSTM inference,
and writes results/evaluation.csv and results/summary.json.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import time
from pathlib import Path
from statistics import mean

# Make sure project root is importable
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.risk_engine.risk_engine import compute_risk, haversine_m
from backend.risk_engine.predictive_collision import predict_collision
from ml.inference.predict import predict_future_positions

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# Scenario definitions (inline, no MQTT needed)
# ─────────────────────────────────────────────

def make_boat(boat_id, lat, lon, speed, heading, obstacle=0):
    return {"boat_id": boat_id, "lat": lat, "lon": lon,
            "speed": speed, "heading": heading, "obstacle": obstacle}

def step_boat(b):
    rad = math.radians(b["heading"])
    b["lat"] += (b["speed"] * math.cos(rad)) / 111_320
    b["lon"] += (b["speed"] * math.sin(rad)) / (111_320 * math.cos(math.radians(b["lat"])))

SCENARIOS = {
    "HEAD_ON": {
        "init": lambda: [
            make_boat("B01", 9.5910, 76.5211, 8.0, 90),
            make_boat("B02", 9.5910, 76.5240, 8.0, 270),
        ],
        "update": lambda states, tick: None,
        "ticks": 60,
    },
    "CROSSING": {
        "init": lambda: [
            make_boat("B01", 9.5910, 76.5214, 4.6, 85),
            make_boat("B02", 9.5904, 76.5228, 4.4, 350),
        ],
        "update": lambda states, tick: states[1].__setitem__("heading", states[1]["heading"] - 0.4) if tick > 30 else None,
        "ticks": 70,
    },
    "BLIND_TURN": {
        "init": lambda: [
            make_boat("B01", 9.5907, 76.5211, 3.8, 30, obstacle=1),
            make_boat("B02", 9.5919, 76.5220, 3.5, 215, obstacle=1),
        ],
        "update": lambda states, tick: [
            states[0].__setitem__("heading", states[0]["heading"] + 1.4),
            states[1].__setitem__("heading", states[1]["heading"] - 1.2),
        ],
        "ticks": 80,
    },
    "SUDDEN_STOP": {
        "init": lambda: [
            make_boat("B01", 9.5910, 76.5212, 6.0, 80),
            make_boat("B02", 9.5911, 76.5224, 5.8, 80),
        ],
        "update": lambda states, tick: states[1].__setitem__(
            "speed", max(0.0, states[1]["speed"] - 0.8)
        ) if tick > 15 else None,
        "ticks": 60,
    },
}

# ─────────────────────────────────────────────
# Simulation + evaluation
# ─────────────────────────────────────────────

def run_scenario(name: str, cfg: dict) -> dict:
    states = cfg["init"]()
    ticks = cfg["ticks"]

    histories = {s["boat_id"]: [] for s in states}
    risk_values, ttc_values, pred_errors = [], [], []
    alert_counts = {"SAFE": 0, "WARNING": 0, "DANGER": 0}
    collision_predictions = 0
    prediction_count = 0
    latencies_ms = []

    timeline_rows = []

    for tick in range(ticks):
        cfg["update"](states, tick)
        for s in states:
            step_boat(s)
            histories[s["boat_id"]].append(dict(s))

        a, b = states[0], states[1]
        risk_info = compute_risk(a, b)
        risk = risk_info["risk"]
        ttc  = risk_info["ttc"]
        dist = risk_info["distance_m"]

        risk_values.append(risk)
        alert_counts[risk_info["warning"]] += 1
        if ttc is not None:
            ttc_values.append(ttc)

        # Run LSTM prediction when risk is elevated
        future_dist = None
        pred_error = None
        if risk > 0.4 or dist < 100:
            t0 = time.perf_counter()
            hist_a = histories[a["boat_id"]][-10:]
            hist_b = histories[b["boat_id"]][-10:]
            traj_a = predict_future_positions(hist_a)
            traj_b = predict_future_positions(hist_b)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

            collision = predict_collision(traj_a, traj_b)
            future_dist = collision["future_distance"]
            if collision["alert_state"] != "SAFE":
                collision_predictions += 1
            prediction_count += 1

            # Prediction error: compare predicted step-1 position to actual step-1
            if len(traj_a) > 0 and len(histories[a["boat_id"]]) > 1:
                actual_next = histories[a["boat_id"]][-1]
                err = haversine_m(traj_a[0]["lat"], traj_a[0]["lon"],
                                  actual_next["lat"], actual_next["lon"])
                pred_errors.append(err)
                pred_error = round(err, 2)

        timeline_rows.append({
            "t": round(tick * 0.5, 1),
            "distance": dist,
            "future_distance": future_dist or 0,
            "risk": risk,
            "ttc": ttc,
            "prediction_error": pred_error or 0,
            "alert": risk_info["warning"],
        })

    # Write timeline CSV
    tl_path = RESULTS_DIR / f"{name.lower()}.csv"
    with tl_path.open("w", newline="") as fh:
        cols = ["t", "distance", "future_distance", "risk", "ttc", "prediction_error", "alert"]
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(timeline_rows)

    danger_count  = alert_counts["DANGER"]
    warning_count = alert_counts["WARNING"]
    total_alerts  = danger_count + warning_count
    high_risk     = sum(1 for r in risk_values if r >= 0.5)

    precision = round(danger_count / max(total_alerts, collision_predictions), 3) if total_alerts or collision_predictions else 0.0
    recall    = round(danger_count / high_risk, 3) if high_risk else 0.0
    f1        = round(2 * precision * recall / (precision + recall), 3) if (precision + recall) else 0.0

    return {
        "scenario": name,
        "alerts": total_alerts,
        "predictions": prediction_count,
        "collisions": collision_predictions,
        "avg_risk": round(mean(risk_values), 3),
        "avg_ttc": round(mean(ttc_values), 2) if ttc_values else 0.0,
        "avg_prediction_error": round(mean(pred_errors), 3) if pred_errors else 0.0,
        "latency": round(mean(latencies_ms), 2) if latencies_ms else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_alarm_rate": round(warning_count / total_alerts, 3) if total_alerts else 0.0,
        "danger_alerts": danger_count,
        "warning_alerts": warning_count,
    }


def main():
    print("Running standalone evaluation across all 4 scenarios...\n")
    all_results = []

    for name, cfg in SCENARIOS.items():
        print(f"  [{name}] simulating {cfg['ticks']} ticks...", end=" ", flush=True)
        t0 = time.time()
        result = run_scenario(name, cfg)
        elapsed = round(time.time() - t0, 2)
        print(f"done ({elapsed}s) — risk={result['avg_risk']}  alerts={result['alerts']}  "
              f"collisions={result['collisions']}  P={result['precision']}  F1={result['f1']}")
        all_results.append(result)

    # evaluation.csv
    csv_cols = ["scenario", "alerts", "predictions", "collisions", "avg_risk", "latency", "precision"]
    with (RESULTS_DIR / "evaluation.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_cols)
        writer.writeheader()
        for r in all_results:
            writer.writerow({c: r.get(c, 0) for c in csv_cols})

    # summary.json  — aggregate across all scenarios
    summary = {
        "scenarios": len(all_results),
        "total_alerts": sum(r["alerts"] for r in all_results),
        "total_predictions": sum(r["predictions"] for r in all_results),
        "total_collisions": sum(r["collisions"] for r in all_results),
        "avg_risk": round(mean(r["avg_risk"] for r in all_results), 3),
        "avg_ttc": round(mean(r["avg_ttc"] for r in all_results if r["avg_ttc"]), 2),
        "avg_prediction_error_m": round(mean(r["avg_prediction_error"] for r in all_results), 3),
        "avg_latency_ms": round(mean(r["latency"] for r in all_results), 2),
        "avg_precision": round(mean(r["precision"] for r in all_results), 3),
        "avg_recall": round(mean(r["recall"] for r in all_results), 3),
        "avg_f1": round(mean(r["f1"] for r in all_results), 3),
        "per_scenario": all_results,
    }
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    print("\n✓ evaluation.csv and summary.json written to results/")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

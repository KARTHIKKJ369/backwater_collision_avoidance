from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

from backend.avoidance.recommendation import recommend_action
from backend.database import db
from backend.predict_controller import evaluate_pair, track_ack, track_recommendation, track_warning
from backend.risk_engine.alerts import alert_manager

from backend.risk_engine.risk_engine import compute_risk
from backend.risk_engine.ttc import compute_ttc
from backend.weather.weather_client import get_weather_for_position

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_SENSOR = "boats/+/sensor"
TOPIC_PREDICT = "boats/{id}/predict"
TOPIC_ALERT = "boats/{id}/alert"
TOPIC_STATUS = "boats/{id}/status"
TOPIC_RECOMMENDATION = "boats/{id}/recommendation"
TOPIC_ACK = "boats/+/ack"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="backend-api")
_latest: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_started = False


def _boat_id_from_topic(topic: str) -> str | None:
    parts = topic.split("/")
    if len(parts) >= 3 and parts[0] == "boats":
        return parts[1]
    return None


def publish(topic: str, payload: dict[str, Any] | list[Any]) -> None:
    client.publish(topic, json.dumps(payload), qos=0, retain=False)


def store_message(payload: dict[str, Any]) -> dict[str, Any]:
    boat_id = str(payload["boat_id"])
    payload["boat_id"] = boat_id
    scenario = str(payload.get("scenario", "LIVE"))
    payload["scenario"] = scenario
    risk = 0.0
    risk_result: dict[str, Any] | None = None
    alert_id: int | None = None
    other_boat_id: str | None = None

    # Fetch weather once per message (cached — no extra HTTP per tick)
    weather = get_weather_for_position(float(payload["lat"]), float(payload["lon"]))

    with _lock:
        for other_id, other_payload in _latest.items():
            if other_id == boat_id:
                continue
            candidate = compute_risk(payload, other_payload, weather=weather)
            if candidate["risk"] > risk:
                risk = candidate["risk"]
                risk_result = candidate
                other_boat_id = other_id
        _latest[boat_id] = payload.copy()

    telemetry_id = db.insert_telemetry(payload, risk=risk)
    prediction_result: dict[str, Any] | None = None

    if risk_result and other_boat_id:
        ttc_result = compute_ttc(risk_result["distance_m"], risk_result["relative_speed"])
        ttc_value = ttc_result["ttc"] if ttc_result else None
        ttc_payload = ttc_result if ttc_result else {"ttc": None, "state": "SAFE"}
        prediction_result = evaluate_pair(
            boat_id,
            other_boat_id,
            risk_result["distance_m"],
            risk_result["risk"],
            ttc_value,
            scenario,
            speed_a=float(payload.get("speed", 0.0)),
            speed_b=float(other_payload.get("speed", 0.0)),
        )
        collision = prediction_result.get("collision") if prediction_result else None

        if collision:
            # alert_state is already computed by predict_collision using the
            # dynamic safety/warning radius — use it directly rather than
            # reclassifying via classify_future_distance (which returns
            # "EARLY_WARNING" and would cause a KeyError in should_alert).
            state = collision["alert_state"]

            # ── Ghost-prediction guard ──────────────────────────────────────────
            # When the LSTM/dead-reckoning has too little history it can predict a
            # near-zero future separation while boats are still far apart (e.g.
            # future_distance=1.69 m at actual distance=222 m in HEAD_ON at t=2.5).
            # Suppress the alert if future separation < 5 % of current real
            # distance AND boats are still more than 80 m away.
            current_distance = risk_result.get("distance_m", 0.0)
            future_dist = collision["future_distance"]
            if (
                future_dist > 0
                and future_dist < current_distance * 0.05
                and current_distance > 80
            ):
                state = "SAFE"  # prediction not yet reliable — skip alert

            if state != "SAFE":
                track_warning()

            action = recommend_action(
                risk_result["heading_difference"],
                prediction_result.get("prediction_a", {}).get("positions", []),
                ttc_value,
            )
            if action != "MAINTAIN":
                track_recommendation()
                db.insert_recommendation(boat_id, payload["timestamp"], action, scenario, state)
                publish(
                    TOPIC_RECOMMENDATION.format(id=boat_id),
                    {
                        "boat_id": boat_id,
                        "other_boat_id": other_boat_id,
                        "action": action,
                        "accepted": False,
                        "alert_state": state,
                        "ttc": ttc_value,
                        "future_distance": collision["future_distance"],
                    },
                )

            pair_key = ":".join(sorted([boat_id, other_boat_id]))
            if alert_manager.should_alert(pair_key, state):
                ttc_text = f"{ttc_value:.2f}" if ttc_value is not None else "N/A"
                weather_desc = weather.get("description", "unknown") if weather else "unavailable"
                message = (
                    f"{state} cooperative collision risk with {other_boat_id}: "
                    f"{collision['future_distance']} m future separation, "
                    f"TTC {ttc_text} s, action {action}, "
                    f"weather: {weather_desc} (factor {risk_result.get('weather_factor', 1.0):.2f})"
                )
                alert_id = alert_manager.save_alert(
                    boat_id,
                    payload["timestamp"],
                    state,
                    message,
                    key=pair_key,
                    scenario=scenario,
                )
                publish(
                    TOPIC_ALERT.format(id=boat_id),
                    {
                        "boat_id": boat_id,
                        "other_boat_id": other_boat_id,
                        **risk_result,
                        **ttc_payload,
                        **collision,
                        "action": action,
                        "alert_state": state,
                        "message": message,
                        "weather": weather,
                    },
                )

    publish(TOPIC_STATUS.format(id=boat_id), {"boat_id": boat_id, "risk": risk, "timestamp": payload["timestamp"]})
    return {
        "telemetry_id": telemetry_id,
        "risk": risk,
        "risk_result": risk_result,
        "prediction_result": prediction_result,
        "alert_id": alert_id,
    }


def _on_connect(mqtt_client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
    mqtt_client.subscribe(TOPIC_SENSOR)
    mqtt_client.subscribe(TOPIC_ACK)


def _on_message(mqtt_client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        topic_boat_id = _boat_id_from_topic(message.topic)
        if topic_boat_id:
            payload.setdefault("boat_id", topic_boat_id)
        if message.topic.endswith("/ack"):
            accepted = bool(payload.get("accepted", False))
            action = str(payload.get("action", ""))
            if accepted and action:
                db.mark_recommendation_accepted(payload["boat_id"], action)
            track_ack(accepted)
        else:
            store_message(payload)
    except Exception as exc:
        print(f"MQTT message handling failed on {message.topic}: {exc}", flush=True)


def subscribe() -> None:
    global _started
    if _started:
        return
    client.on_connect = _on_connect
    client.on_message = _on_message

    for attempt in range(20):
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            _started = True
            print(f"MQTT connected to {MQTT_HOST}:{MQTT_PORT}", flush=True)
            return
        except OSError:
            time.sleep(min(5, attempt + 1))
    raise RuntimeError(f"Unable to connect to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

from backend.database import db
from backend.predict_controller import evaluate_pair
from backend.risk_engine.alerts import alert_manager
from backend.risk_engine.risk_engine import compute_risk
from backend.risk_engine.ttc import compute_ttc

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_SENSOR = "boats/+/sensor"
TOPIC_PREDICT = "boats/{id}/predict"
TOPIC_ALERT = "boats/{id}/alert"
TOPIC_STATUS = "boats/{id}/status"

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
    risk = 0.0
    risk_result: dict[str, Any] | None = None
    alert_id: int | None = None
    other_boat_id: str | None = None

    with _lock:
        for other_id, other_payload in _latest.items():
            if other_id == boat_id:
                continue
            candidate = compute_risk(payload, other_payload)
            if candidate["risk"] > risk:
                risk = candidate["risk"]
                risk_result = candidate
                other_boat_id = other_id
        _latest[boat_id] = payload.copy()

    telemetry_id = db.insert_telemetry(payload, risk=risk)
    prediction_result: dict[str, Any] | None = None

    if risk_result and other_boat_id:
        ttc = compute_ttc(risk_result["distance_m"], risk_result["relative_speed"])
        prediction_result = evaluate_pair(boat_id, other_boat_id, risk_result["distance_m"], risk_result["risk"])
        collision = prediction_result.get("collision") if prediction_result else None

        if collision:
            state = alert_manager.transition_state(future_distance=collision["future_distance"])
            pair_key = ":".join(sorted([boat_id, other_boat_id]))
            if alert_manager.should_alert(pair_key, state):
                message = (
                    f"{state} predictive collision risk with {other_boat_id}: "
                    f"{collision['future_distance']} m future separation, "
                    f"TTC {collision['time_to_collision']} s"
                )
                alert_id = alert_manager.save_alert(boat_id, payload["timestamp"], state, message, key=pair_key)
                publish(
                    TOPIC_ALERT.format(id=boat_id),
                    {
                        "boat_id": boat_id,
                        "other_boat_id": other_boat_id,
                        **risk_result,
                        **ttc,
                        **collision,
                        "message": message,
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


def _on_message(mqtt_client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        topic_boat_id = _boat_id_from_topic(message.topic)
        if topic_boat_id:
            payload.setdefault("boat_id", topic_boat_id)
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

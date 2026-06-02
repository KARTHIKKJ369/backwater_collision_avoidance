from __future__ import annotations

import time
from typing import Any

from backend.database import db

SAFE = "SAFE"
WARNING = "WARNING"
DANGER = "DANGER"


class AlertManager:
    def __init__(self, cooldown_seconds: float = 10.0) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._states: dict[str, str] = {}
        self._last_alert_at: dict[str, float] = {}

    def transition_state(self, risk: float | None = None, future_distance: float | None = None) -> str:
        if future_distance is not None:
            if future_distance > 100:
                return SAFE
            if future_distance >= 50:
                return WARNING
            return DANGER

        score = risk or 0.0
        if score < 0.4:
            return SAFE
        if score < 0.7:
            return WARNING
        return DANGER

    def should_alert(self, key: str, new_state: str, now: float | None = None) -> bool:
        now = now or time.time()
        old_state = self._states.get(key, SAFE)
        last_alert_at = self._last_alert_at.get(key, 0.0)

        if new_state == old_state:
            return False
        if new_state == SAFE:
            self._states[key] = new_state
            return False
        if now - last_alert_at < self.cooldown_seconds:
            return False
        return True

    def save_alert(
        self,
        boat_id: str,
        timestamp: float,
        severity: str,
        message: str,
        key: str | None = None,
        scenario: str = "LIVE",
    ) -> int:
        alert_id = db.insert_alert(boat_id, timestamp, severity, message, scenario)
        state_key = key or boat_id
        self._states[state_key] = severity
        self._last_alert_at[state_key] = time.time()
        return alert_id


alert_manager = AlertManager()

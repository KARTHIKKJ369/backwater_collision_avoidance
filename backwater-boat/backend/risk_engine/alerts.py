from __future__ import annotations

import time
from typing import Any

from backend.database import db

SAFE = "SAFE"
WARNING = "WARNING"
DANGER = "DANGER"

# Severity ordering used for hysteresis comparisons
_SEVERITY_RANK = {SAFE: 0, WARNING: 1, DANGER: 2}


class AlertManager:
    def __init__(self, cooldown_seconds: float = 10.0, confirm_ticks: int = 2) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.confirm_ticks = confirm_ticks
        self._states: dict[str, str] = {}
        self._last_alert_at: dict[str, float] = {}
        # consecutive non-SAFE ticks seen for each pair before an alert fires
        self._pending: dict[str, int] = {}

    def transition_state(self, risk: float | None = None, future_distance: float | None = None) -> str:
        if future_distance is not None:
            if future_distance > 100:
                return SAFE
            if future_distance >= 50:
                return WARNING
            return DANGER

        score = risk or 0.0
        if score < 0.45:
            return SAFE
        if score <= 0.65:
            return WARNING
        return DANGER

    def should_alert(self, key: str, new_state: str, now: float | None = None) -> bool:
        now = now or time.time()
        old_state = self._states.get(key, SAFE)
        last_alert_at = self._last_alert_at.get(key, 0.0)

        # Always track current state so the next tick compares against reality,
        # not a stale value that would re-trigger a suppressed transition.
        self._states[key] = new_state

        # Going back to SAFE: reset confirmation counter, no alert needed
        if new_state == SAFE:
            self._pending[key] = 0
            return False

        # No change in severity: suppress (but still increment pending so an
        # existing escalation keeps building its confirmation count)
        if new_state == old_state:
            return False

        # Only escalations (SAFE→WARNING, SAFE→DANGER, WARNING→DANGER) fire.
        # A downgrade (DANGER→WARNING) is noise from a threshold-straddling
        # risk score and must not trigger a new alert.
        if _SEVERITY_RANK[new_state] <= _SEVERITY_RANK[old_state]:
            return False

        # Cooldown applies even to genuine escalations.
        if now - last_alert_at < self.cooldown_seconds:
            return False

        # Confirmation window: require confirm_ticks consecutive non-SAFE readings
        # before firing.  DANGER bypasses (only needs 1 tick) to preserve recall
        # in fast-closing scenarios such as HEAD_ON at high speed.
        pending = self._pending.get(key, 0) + 1
        self._pending[key] = pending
        if new_state == WARNING and pending < self.confirm_ticks:
            return False

        # Reset counter once an alert fires
        self._pending[key] = 0
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
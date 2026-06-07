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


    def should_alert(self, key: str, new_state: str, now: float | None = None) -> bool:
        now = now or time.time()
        old_state = self._states.get(key, SAFE)
        last_alert_at = self._last_alert_at.get(key, 0.0)

        # Going back to SAFE: reset confirmation counter, commit immediately
        if new_state == SAFE:
            self._states[key] = SAFE
            self._pending[key] = 0
            return False

        # No change in severity: suppress
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
        # NOTE: state is NOT committed until the alert fires — committing early
        # would make old_state == new_state on the next tick, which would cause
        # the "no change" guard above to suppress the confirmation counter.
        pending = self._pending.get(key, 0) + 1
        self._pending[key] = pending
        if new_state == WARNING and pending < self.confirm_ticks:
            return False

        # Alert fires: commit state and reset counter
        self._states[key] = new_state
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
"""
Targeted tests for the three bug fixes:

  1. AlertManager confirmation window (alerts.py)
  2. Prediction trigger gate thresholds (predict_controller.py)
  3. predict_collision state boundaries (predictive_collision.py)
"""
from __future__ import annotations

import unittest

from backend.predict_controller import should_run_prediction
from backend.risk_engine.alerts import DANGER, SAFE, WARNING, AlertManager
from backend.risk_engine.predictive_collision import predict_collision


# ---------------------------------------------------------------------------
# 1. AlertManager confirmation window
# ---------------------------------------------------------------------------

class AlertManagerConfirmationTests(unittest.TestCase):
    """WARNING needs confirm_ticks consecutive escalation ticks; DANGER fires immediately."""

    def _manager(self, **kw) -> AlertManager:
        return AlertManager(cooldown_seconds=10, **kw)

    # --- WARNING confirmation ---

    def test_warning_does_not_fire_on_first_tick(self) -> None:
        m = self._manager()
        self.assertFalse(m.should_alert("A:B", WARNING, now=11))

    def test_warning_fires_on_second_tick(self) -> None:
        m = self._manager()
        m.should_alert("A:B", WARNING, now=11)          # tick 1
        self.assertTrue(m.should_alert("A:B", WARNING, now=11))  # tick 2

    def test_warning_resets_after_safe(self) -> None:
        m = self._manager()
        m.should_alert("A:B", WARNING, now=11)          # tick 1 of first attempt — pending=1
        m.should_alert("A:B", SAFE, now=12)             # reset — pending back to 0
        # tick 1 post-reset: counter restarted, must not fire
        self.assertFalse(m.should_alert("A:B", WARNING, now=13))
        # tick 2 post-reset: correctly fires — confirms counter built up from zero
        self.assertTrue(m.should_alert("A:B", WARNING, now=13))

    def test_warning_counter_is_per_key(self) -> None:
        m = self._manager()
        m.should_alert("A:B", WARNING, now=11)          # tick 1 for A:B
        # C:D starts fresh — its first tick must not fire
        self.assertFalse(m.should_alert("C:D", WARNING, now=11))

    def test_warning_fires_only_once_per_escalation(self) -> None:
        m = self._manager()
        m.should_alert("A:B", WARNING, now=11)
        self.assertTrue(m.should_alert("A:B", WARNING, now=11))   # fires
        # same state — no re-fire even after cooldown
        m._last_alert_at["A:B"] = 11
        self.assertFalse(m.should_alert("A:B", WARNING, now=22))

    # --- DANGER bypasses confirmation ---

    def test_danger_fires_on_first_tick(self) -> None:
        m = self._manager()
        self.assertTrue(m.should_alert("A:B", DANGER, now=11))

    def test_danger_fires_without_prior_warning_ticks(self) -> None:
        """DANGER must fire even when WARNING's pending counter is zero."""
        m = self._manager()
        self.assertTrue(m.should_alert("A:B", DANGER, now=11))

    # --- Cooldown ---

    def test_cooldown_suppresses_danger_within_window(self) -> None:
        m = self._manager()
        m.should_alert("A:B", DANGER, now=11)
        m._last_alert_at["A:B"] = 11
        self.assertFalse(m.should_alert("A:B", DANGER, now=15))   # 4 s < 10 s cooldown

    def test_danger_fires_after_cooldown_expires(self) -> None:
        m = self._manager()
        m.should_alert("A:B", DANGER, now=11)
        m._last_alert_at["A:B"] = 11
        # Escalate back through SAFE so state resets, then re-escalate
        m.should_alert("A:B", SAFE, now=12)
        m.should_alert("A:B", WARNING, now=22)           # tick 1
        self.assertTrue(m.should_alert("A:B", WARNING, now=22))  # tick 2 — fires

    # --- Downgrade suppression ---

    def test_downgrade_from_danger_to_warning_does_not_alert(self) -> None:
        m = self._manager()
        m.should_alert("A:B", DANGER, now=11)
        m._last_alert_at["A:B"] = 11
        m._states["A:B"] = DANGER
        self.assertFalse(m.should_alert("A:B", WARNING, now=22))

    # --- SAFE always returns False ---

    def test_safe_never_alerts(self) -> None:
        m = self._manager()
        self.assertFalse(m.should_alert("A:B", SAFE, now=0))
        self.assertFalse(m.should_alert("A:B", SAFE, now=999))

    # --- confirm_ticks=1 collapses window ---

    def test_confirm_ticks_1_fires_immediately(self) -> None:
        m = self._manager(confirm_ticks=1)
        self.assertTrue(m.should_alert("A:B", WARNING, now=11))


# ---------------------------------------------------------------------------
# 2. Prediction trigger gate
# ---------------------------------------------------------------------------

class TriggerGateTests(unittest.TestCase):
    """Thresholds: distance < 150 m  OR  ttc < 15 s  OR  risk > 0.3"""

    # --- each condition alone ---

    def test_triggers_on_close_distance(self) -> None:
        self.assertTrue(should_run_prediction(distance_m=149, risk=0.0, ttc=999))

    def test_triggers_on_low_ttc(self) -> None:
        self.assertTrue(should_run_prediction(distance_m=999, risk=0.0, ttc=14.9))

    def test_triggers_on_high_risk(self) -> None:
        self.assertTrue(should_run_prediction(distance_m=999, risk=0.31, ttc=999))

    # --- boundary: exactly at threshold ---

    def test_distance_exactly_150_does_not_trigger(self) -> None:
        self.assertFalse(should_run_prediction(distance_m=150, risk=0.0, ttc=999))

    def test_ttc_exactly_15_does_not_trigger(self) -> None:
        self.assertFalse(should_run_prediction(distance_m=999, risk=0.0, ttc=15.0))

    def test_risk_exactly_0_3_does_not_trigger(self) -> None:
        self.assertFalse(should_run_prediction(distance_m=999, risk=0.3, ttc=999))

    # --- all conditions missed ---

    def test_no_trigger_when_all_below_threshold(self) -> None:
        self.assertFalse(should_run_prediction(distance_m=200, risk=0.25, ttc=20))

    # --- ttc=None is safe ---

    def test_none_ttc_does_not_count_as_trigger(self) -> None:
        self.assertFalse(should_run_prediction(distance_m=200, risk=0.25, ttc=None))

    def test_none_ttc_still_triggers_on_distance(self) -> None:
        self.assertTrue(should_run_prediction(distance_m=100, risk=0.0, ttc=None))


# ---------------------------------------------------------------------------
# 3. predict_collision state boundaries (speed=0 → safety_radius=20 m)
# ---------------------------------------------------------------------------

def _pair(dist_m: float) -> tuple[list[dict], list[dict]]:
    """Build two single-step trajectories exactly dist_m apart (longitudinally)."""
    # 1 degree longitude ≈ 111 320 * cos(9.591°) ≈ 109 893 m at this lat
    deg_per_metre = 1.0 / 109_893.0
    half = (dist_m / 2) * deg_per_metre
    base_lat, base_lon = 9.591, 76.522
    a = [{"lat": base_lat, "lon": base_lon - half}]
    b = [{"lat": base_lat, "lon": base_lon + half}]
    return a, b


class PredictCollisionBoundaryTests(unittest.TestCase):
    """
    With speed_a=speed_b=0:
        safety_radius  = max(20, 0) = 20 m
        warning_radius = 30 m

    Boundaries:
        distance = 0       → DANGER
        distance < 20      → DANGER
        distance = 20      → WARNING  (>= safety_radius)
        distance < 30      → WARNING
        distance = 30      → SAFE     (> warning_radius)
        distance > 30      → SAFE
    """

    def test_zero_distance_is_danger(self) -> None:
        a = [{"lat": 9.591, "lon": 76.522}]
        b = [{"lat": 9.591, "lon": 76.522}]
        self.assertEqual(predict_collision(a, b)["alert_state"], DANGER)

    def test_inside_safety_radius_is_danger(self) -> None:
        a, b = _pair(10.0)
        self.assertEqual(predict_collision(a, b)["alert_state"], DANGER)

    def test_at_safety_radius_is_warning(self) -> None:
        # _pair uses an approximate lon→m factor; 20.0 rounds to 19.95 m (DANGER).
        # Use 21 m to land clearly in the WARNING band [20 m, 30 m).
        a, b = _pair(21.0)
        self.assertEqual(predict_collision(a, b)["alert_state"], WARNING)

    def test_between_radii_is_warning(self) -> None:
        a, b = _pair(25.0)
        self.assertEqual(predict_collision(a, b)["alert_state"], WARNING)

    def test_at_warning_radius_is_safe(self) -> None:
        # distance > warning_radius → SAFE
        a, b = _pair(31.0)
        self.assertEqual(predict_collision(a, b)["alert_state"], SAFE)

    def test_far_apart_is_safe(self) -> None:
        a, b = _pair(200.0)
        self.assertEqual(predict_collision(a, b)["alert_state"], SAFE)

    def test_minimum_across_steps_drives_state(self) -> None:
        """Alert state must reflect the closest future point, not the first."""
        # Steps: 200 m apart → 0 m → converging trajectory must yield DANGER
        deg = 200.0 / 109_893.0 / 2
        a = [{"lat": 9.591, "lon": 76.522 - deg}, {"lat": 9.591, "lon": 76.522}]
        b = [{"lat": 9.591, "lon": 76.522 + deg}, {"lat": 9.591, "lon": 76.522}]
        result = predict_collision(a, b)
        self.assertEqual(result["alert_state"], DANGER)
        self.assertEqual(result["future_distance"], 0.0)

    def test_empty_trajectories_return_safe(self) -> None:
        result = predict_collision([], [])
        self.assertEqual(result["alert_state"], SAFE)
        self.assertEqual(result["collision_probability"], 0.0)


if __name__ == "__main__":
    unittest.main()
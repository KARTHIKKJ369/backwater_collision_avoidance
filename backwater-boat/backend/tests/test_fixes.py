"""
Targeted tests for the three bug fixes:

  1. AlertManager confirmation window (alerts.py)
  2. Prediction trigger gate thresholds (predict_controller.py)
  3. predict_collision state boundaries (predictive_collision.py)
"""
from __future__ import annotations

import math
import unittest

from backend.predict_controller import should_run_prediction
from backend.risk_engine.alerts import DANGER, SAFE, WARNING, AlertManager
from backend.risk_engine.predictive_collision import predict_collision
from ml.inference.predict import (
    FORECAST_STEPS,
    _haversine_m,
    _sanity_check,
    _dead_reckon,
    predict_future_positions,
    _MIN_FLOOR_M,
    _SANITY_FACTOR,
    _DT_SECONDS,
)


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



# ---------------------------------------------------------------------------
# 4. Physical sanity-check helpers (_haversine_m, _sanity_check)
# ---------------------------------------------------------------------------

# Fixed point in the training region (Alappuzha backwaters)
_BASE_LAT = 9.592
_BASE_LON = 76.525


def _shift_lat(lat: float, metres: float) -> float:
    """Return latitude displaced north by *metres*."""
    return lat + metres / 111_320.0


def _shift_lon(lon: float, lat: float, metres: float) -> float:
    """Return longitude displaced east by *metres* at a given latitude."""
    return lon + metres / (111_320.0 * math.cos(math.radians(lat)))


def _make_points(origin_lat: float, origin_lon: float,
                 displacement_m: float, n: int) -> list[dict]:
    """
    Build *n* forecast points, each *displacement_m* metres north of the origin.
    All steps land at the same location so the step-1 kinematic budget is the
    binding constraint.
    """
    lat = _shift_lat(origin_lat, displacement_m)
    return [{"lat": lat, "lon": origin_lon, "confidence": 0.9}] * n


class HaversineTests(unittest.TestCase):
    """_haversine_m returns correct metric distances."""

    def test_zero_distance(self) -> None:
        self.assertEqual(_haversine_m(_BASE_LAT, _BASE_LON, _BASE_LAT, _BASE_LON), 0.0)

    def test_100m_north(self) -> None:
        lat2 = _shift_lat(_BASE_LAT, 100.0)
        self.assertAlmostEqual(_haversine_m(_BASE_LAT, _BASE_LON, lat2, _BASE_LON), 100.0, delta=0.5)

    def test_500m_east(self) -> None:
        lon2 = _shift_lon(_BASE_LON, _BASE_LAT, 500.0)
        self.assertAlmostEqual(_haversine_m(_BASE_LAT, _BASE_LON, _BASE_LAT, lon2), 500.0, delta=2.0)

    def test_symmetry(self) -> None:
        lat2 = _shift_lat(_BASE_LAT, 200.0)
        d1 = _haversine_m(_BASE_LAT, _BASE_LON, lat2, _BASE_LON)
        d2 = _haversine_m(lat2, _BASE_LON, _BASE_LAT, _BASE_LON)
        self.assertAlmostEqual(d1, d2, places=6)


class SanityCheckUnitTests(unittest.TestCase):
    """_sanity_check accepts good trajectories and rejects OOD ones."""

    # --- passes ---

    def test_accepts_points_within_kinematic_budget(self) -> None:
        # speed 5 m/s, step-1 budget = 5 × 1 × 2.5 = 12.5 m → floor 50 m applies.
        # 30 m is within the 50 m floor.
        pts = _make_points(_BASE_LAT, _BASE_LON, 30.0, FORECAST_STEPS)
        self.assertTrue(_sanity_check(pts, _BASE_LAT, _BASE_LON, speed_ms=5.0))

    def test_accepts_stationary_boat_within_floor(self) -> None:
        # Speed=0 → all budgets collapse to _MIN_FLOOR_M; 30 m must still pass.
        pts = _make_points(_BASE_LAT, _BASE_LON, 30.0, FORECAST_STEPS)
        self.assertTrue(_sanity_check(pts, _BASE_LAT, _BASE_LON, speed_ms=0.0))

    def test_accepts_origin_itself(self) -> None:
        pts = [{"lat": _BASE_LAT, "lon": _BASE_LON, "confidence": 1.0}] * FORECAST_STEPS
        self.assertTrue(_sanity_check(pts, _BASE_LAT, _BASE_LON, speed_ms=0.0))

    # --- rejects ---

    def test_rejects_1km_displacement_at_low_speed(self) -> None:
        # 1 km at step-1, speed 2 m/s: budget = max(2×1×2.5, 50) = 50 m → reject.
        pts = _make_points(_BASE_LAT, _BASE_LON, 1_000.0, FORECAST_STEPS)
        self.assertFalse(_sanity_check(pts, _BASE_LAT, _BASE_LON, speed_ms=2.0))

    def test_rejects_ood_5sigma_displacement(self) -> None:
        # 5σ × lat_sd ≈ 1.05 km — the exact failure mode described in the diagnosis.
        lat_sd = 0.0021
        displaced_lat = _BASE_LAT + 5 * lat_sd
        pts = [{"lat": displaced_lat, "lon": _BASE_LON, "confidence": 0.5}] * FORECAST_STEPS
        self.assertFalse(_sanity_check(pts, _BASE_LAT, _BASE_LON, speed_ms=3.0))

    def test_rejects_points_beyond_floor_for_stationary_boat(self) -> None:
        pts = _make_points(_BASE_LAT, _BASE_LON, 200.0, FORECAST_STEPS)
        self.assertFalse(_sanity_check(pts, _BASE_LAT, _BASE_LON, speed_ms=0.0))

    def test_step1_budget_is_binding_constraint(self) -> None:
        # 100 m < step-15 budget (187.5 m) but > step-1 floor (50 m) → reject.
        pts = _make_points(_BASE_LAT, _BASE_LON, 100.0, FORECAST_STEPS)
        self.assertFalse(_sanity_check(pts, _BASE_LAT, _BASE_LON, speed_ms=5.0))

    def test_exactly_inside_floor_passes(self) -> None:
        pts = _make_points(_BASE_LAT, _BASE_LON, _MIN_FLOOR_M - 0.1, FORECAST_STEPS)
        self.assertTrue(_sanity_check(pts, _BASE_LAT, _BASE_LON, speed_ms=0.0))

    def test_budget_grows_with_speed(self) -> None:
        # 200 m at step 1: budget = max(20×1×2.5, 50) = 50 m → still reject.
        # But at step 15: budget = 20×15×2.5 = 750 m → 200 m would pass if checked alone.
        # The per-step check must catch it at step 1.
        pts = _make_points(_BASE_LAT, _BASE_LON, 200.0, 1)
        self.assertFalse(_sanity_check(pts, _BASE_LAT, _BASE_LON, speed_ms=20.0))


# ---------------------------------------------------------------------------
# 5. Integration: predict_future_positions falls back on OOD model output
# ---------------------------------------------------------------------------

_BASE_HISTORY: list[dict] = [
    {
        "lat":     _BASE_LAT + i * 0.000009,   # ~1 m north each step
        "lon":     _BASE_LON,
        "speed":   2.0,
        "heading": 0.0,
        "ax": 0.0, "ay": 0.0, "az": 9.81,
        "gx": 0.0, "gy": 0.0, "gz": 0.0,
    }
    for i in range(10)   # WINDOW_SIZE = 10
]


class SanityCheckIntegrationTests(unittest.TestCase):
    """predict_future_positions uses dead-reckoning when the model returns OOD output."""

    def _ood_points(self) -> list[dict]:
        """1 km north — impossible for speed=2 m/s."""
        lat_ood = _shift_lat(_BASE_LAT, 1_000.0)
        return [{"lat": lat_ood, "lon": _BASE_LON, "confidence": 0.5}] * FORECAST_STEPS

    def test_ood_tflite_falls_back_to_dead_reckoning(self) -> None:
        import ml.inference.predict as pred_mod

        ood = self._ood_points()
        orig_tflite = pred_mod._predict_tflite
        orig_keras  = pred_mod._predict_keras
        try:
            pred_mod._predict_tflite = lambda *_a, **_kw: ood
            pred_mod._predict_keras  = lambda *_a, **_kw: None
            result = pred_mod.predict_future_positions(_BASE_HISTORY)
        finally:
            pred_mod._predict_tflite = orig_tflite
            pred_mod._predict_keras  = orig_keras

        for pt in result:
            dist = _haversine_m(_BASE_LAT, _BASE_LON, pt["lat"], pt["lon"])
            self.assertLess(
                dist, 200.0,
                msg=f"OOD output not suppressed — got {pt!r} ({dist:.0f} m away)",
            )

    def test_valid_tflite_output_is_returned_as_is(self) -> None:
        import ml.inference.predict as pred_mod

        lat_close = _shift_lat(_BASE_LAT, 10.0)   # 10 m north — well within floor
        valid = [{"lat": lat_close, "lon": _BASE_LON, "confidence": 0.9}] * FORECAST_STEPS

        orig_tflite = pred_mod._predict_tflite
        orig_keras  = pred_mod._predict_keras
        try:
            pred_mod._predict_tflite = lambda *_a, **_kw: valid
            pred_mod._predict_keras  = lambda *_a, **_kw: None
            result = pred_mod.predict_future_positions(_BASE_HISTORY)
        finally:
            pred_mod._predict_tflite = orig_tflite
            pred_mod._predict_keras  = orig_keras

        self.assertEqual(result, valid)

    def test_ood_keras_also_falls_back(self) -> None:
        """The sanity check must also gate the Keras path, not only TFLite."""
        import ml.inference.predict as pred_mod

        ood = self._ood_points()
        orig_tflite = pred_mod._predict_tflite
        orig_keras  = pred_mod._predict_keras
        try:
            pred_mod._predict_tflite = lambda *_a, **_kw: None   # TFLite unavailable
            pred_mod._predict_keras  = lambda *_a, **_kw: ood
            result = pred_mod.predict_future_positions(_BASE_HISTORY)
        finally:
            pred_mod._predict_tflite = orig_tflite
            pred_mod._predict_keras  = orig_keras

        for pt in result:
            dist = _haversine_m(_BASE_LAT, _BASE_LON, pt["lat"], pt["lon"])
            self.assertLess(dist, 200.0)


if __name__ == "__main__":
    unittest.main()
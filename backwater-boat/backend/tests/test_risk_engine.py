from __future__ import annotations

import unittest

from backend.predict_controller import should_run_prediction
from backend.risk_engine.alerts import AlertManager
from backend.risk_engine.predictive_collision import predict_collision
from backend.risk_engine.risk_engine import compute_risk
from backend.risk_engine.ttc import compute_ttc
from ml.inference.predict import trajectory_confidence


class RiskEngineTests(unittest.TestCase):
    def test_alert_manager_alerts_only_on_state_change(self) -> None:
        manager = AlertManager(cooldown_seconds=10)

        self.assertFalse(manager.should_alert("B01:B02", "SAFE", now=0))
        # WARNING requires confirm_ticks=2; first tick must not fire
        self.assertFalse(manager.should_alert("B01:B02", "WARNING", now=11))
        # Second consecutive tick fires
        self.assertTrue(manager.should_alert("B01:B02", "WARNING", now=11))
        # Simulate save_alert recording the alert timestamp
        manager._last_alert_at["B01:B02"] = 11

        self.assertFalse(manager.should_alert("B01:B02", "WARNING", now=20))
        self.assertFalse(manager.should_alert("B01:B02", "DANGER", now=15))
        self.assertTrue(manager.should_alert("B01:B02", "DANGER", now=22))

    def test_ttc_thresholds(self) -> None:
        result_safe = compute_ttc(700, 10)
        result_warning = compute_ttc(400, 10)
        result_danger = compute_ttc(100, 10)

        self.assertIsNotNone(result_safe)
        self.assertIsNotNone(result_warning)
        self.assertIsNotNone(result_danger)
        self.assertEqual(result_safe["state"], "SAFE")
        self.assertEqual(result_warning["state"], "WARNING")
        self.assertEqual(result_danger["state"], "DANGER")

    def test_ttc_returns_none_when_opening(self) -> None:
        self.assertIsNone(compute_ttc(120, 0))
        self.assertIsNone(compute_ttc(120, -5))

    def test_predictive_collision_classifies_future_distance(self) -> None:
        trajectory_a = [{"lat": 9.591, "lon": 76.522}, {"lat": 9.591, "lon": 76.522}]
        # Converge to same point at step 2 → distance=0 → DANGER
        trajectory_b = [{"lat": 9.5918, "lon": 76.522}, {"lat": 9.591, "lon": 76.522}]

        result = predict_collision(trajectory_a, trajectory_b)

        self.assertEqual(result["alert_state"], "DANGER")
        self.assertLess(result["future_distance"], 50)
        self.assertGreater(result["collision_probability"], 0)

    def test_prediction_trigger_gate(self) -> None:
        self.assertTrue(should_run_prediction(distance_m=79, risk=0.1, ttc=100))
        self.assertTrue(should_run_prediction(distance_m=200, risk=0.1, ttc=9.9))
        self.assertTrue(should_run_prediction(distance_m=200, risk=0.51, ttc=100))
        # All three thresholds missed: distance>=150, risk<=0.3, ttc>=15
        self.assertFalse(should_run_prediction(distance_m=200, risk=0.25, ttc=20))

    def test_confidence_varies_with_trajectory_variance(self) -> None:
        stable = [{"lat": 9.591, "lon": 76.522}, {"lat": 9.59101, "lon": 76.52201}]
        variable = [{"lat": 9.591, "lon": 76.522}, {"lat": 9.592, "lon": 76.524}]

        self.assertGreater(trajectory_confidence(stable), trajectory_confidence(variable))

    def test_head_on_risk_uses_closing_ttc(self) -> None:
        boat_a = {"lat": 9.591, "lon": 76.5211, "speed": 8, "heading": 90}
        boat_b = {"lat": 9.591, "lon": 76.5221, "speed": 8, "heading": 270}

        result = compute_risk(boat_a, boat_b)

        self.assertLess(result["ttc"], 10)
        self.assertGreater(result["risk"], 0.5)


if __name__ == "__main__":
    unittest.main()
from __future__ import annotations

import unittest

from backend.predict_controller import should_run_prediction
from backend.risk_engine.alerts import AlertManager
from backend.risk_engine.predictive_collision import predict_collision
from backend.risk_engine.risk_engine import compute_risk


class AcceptancePredictiveFlowTests(unittest.TestCase):
    def test_head_on_flow_reaches_predictive_alert_once(self) -> None:
        boat_a = {"boat_id": "B01", "lat": 9.5910, "lon": 76.5211, "speed": 8.0, "heading": 90, "obstacle": 0}
        boat_b = {"boat_id": "B02", "lat": 9.5910, "lon": 76.5221, "speed": 8.0, "heading": 270, "obstacle": 0}

        risk = compute_risk(boat_a, boat_b)
        self.assertTrue(should_run_prediction(risk["distance_m"], risk["risk"]))

        predicted_a = [
            {"lat": 9.5910, "lon": 76.5213},
            {"lat": 9.5910, "lon": 76.5215},
            {"lat": 9.5910, "lon": 76.5217},
        ]
        predicted_b = [
            {"lat": 9.5910, "lon": 76.5219},
            {"lat": 9.5910, "lon": 76.5217},
            {"lat": 9.5910, "lon": 76.5215},
        ]

        collision = predict_collision(predicted_a, predicted_b)
        self.assertEqual(collision["alert_state"], "DANGER")

        manager = AlertManager(cooldown_seconds=10)
        self.assertTrue(manager.should_alert("B01:B02", collision["alert_state"], now=20))
        manager._states["B01:B02"] = collision["alert_state"]
        manager._last_alert_at["B01:B02"] = 20
        self.assertFalse(manager.should_alert("B01:B02", collision["alert_state"], now=21))


if __name__ == "__main__":
    unittest.main()

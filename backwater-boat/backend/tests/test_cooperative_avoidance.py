from __future__ import annotations

import unittest

from backend.avoidance.recommendation import recommend_action
from backend.risk_engine.early_warning import classify_future_distance


class CooperativeAvoidanceTests(unittest.TestCase):
    def test_early_warning_thresholds(self) -> None:
        self.assertEqual(classify_future_distance(151), "SAFE")
        self.assertEqual(classify_future_distance(120), "EARLY_WARNING")
        self.assertEqual(classify_future_distance(50), "WARNING")
        self.assertEqual(classify_future_distance(29), "DANGER")

    def test_recommendation_outputs(self) -> None:
        path = [{"lat": 9.591, "lon": 76.522}]

        self.assertEqual(recommend_action(180, path, 20), "TURN_RIGHT")
        self.assertEqual(recommend_action(90, path, 20), "TURN_LEFT")
        self.assertEqual(recommend_action(10, path, 8), "SLOW_DOWN")
        self.assertEqual(recommend_action(180, path, 4), "HARD_RIGHT")
        self.assertEqual(recommend_action(10, [], 20), "MAINTAIN")


if __name__ == "__main__":
    unittest.main()

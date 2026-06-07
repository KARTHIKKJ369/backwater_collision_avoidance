from __future__ import annotations

import unittest

from backend.evaluation import evaluate, timeline
from simulator.scenarios import head_on


class EvaluationBenchmarkTests(unittest.TestCase):
    def test_head_on_speed_stays_constant(self) -> None:
        states = [type("State", (), state.copy())() for state in head_on.make_states()]

        head_on.update(states, 25)

        self.assertEqual(states[0].speed, 8.0)
        self.assertEqual(states[1].speed, 8.0)

    @unittest.skip("requires live database seeded by the simulator")
    def test_evaluation_response_shape(self) -> None:
        result = evaluate("LIVE")

        for key in ("precision", "recall", "f1", "false_alarm_rate", "avg_ttc"):
            self.assertIn(key, result)

    @unittest.skip("requires live database seeded by the simulator")
    def test_timeline_returns_list(self) -> None:
        self.assertIsInstance(timeline("LIVE"), list)


if __name__ == "__main__":
    unittest.main()
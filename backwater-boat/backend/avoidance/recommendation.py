from __future__ import annotations

from typing import Any


def emergency_maneuver(relative_heading: float) -> str:
    """Choose an emergency action based on the heading difference between the two boats.

    relative_heading is abs((h1 - h2 + 180) % 360 - 180), in [0, 180].

    ≥150° — head-on: turn hard away from the other vessel.
     20–149° — crossing / angled approach: turn hard left to open the gap.
     <20°  — overtaking / same-direction (e.g. SUDDEN_STOP): slow down is
              safer than a hard turn (which could swing into the other boat)
              or a full stop (which risks the vessel behind running into us).
    """
    if relative_heading >= 150:
        return "HARD_RIGHT"
    if relative_heading >= 20:
        return "HARD_LEFT"
    # Near-parallel geometry (overtaking/sudden-stop): reducing speed opens
    # the gap without the lateral risk of a hard turn at very close range.
    return "SLOW_DOWN"


def recommend_action(relative_heading: float, predicted_path: list[dict[str, Any]], ttc: float | None) -> str:
    if ttc is not None and ttc < 5:
        return emergency_maneuver(relative_heading)
    if not predicted_path:
        return "MAINTAIN"
    if ttc is not None and ttc < 10:
        return "SLOW_DOWN"
    if relative_heading >= 150:
        return "TURN_RIGHT"
    if 30 <= relative_heading < 150:
        return "TURN_LEFT"
    return "MAINTAIN"
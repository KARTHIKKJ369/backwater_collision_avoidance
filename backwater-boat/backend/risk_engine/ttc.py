from __future__ import annotations

from math import inf


def compute_ttc(distance_m: float, relative_speed_mps: float) -> dict[str, float | str]:
    if relative_speed_mps <= 0:
        ttc = inf
    else:
        ttc = distance_m / relative_speed_mps

    if ttc > 60:
        state = "SAFE"
    elif ttc > 20:
        state = "WARNING"
    else:
        state = "DANGER"

    return {"ttc": ttc, "state": state}

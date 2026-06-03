from __future__ import annotations


def make_states() -> list[dict[str, float | int | str]]:
    # B01 follows B02 at ~45 m separation. B02 decelerates sharply after tick 15
    # so B01 closes the gap and triggers a DANGER alert before impact.
    return [
        {"boat_id": "B01", "lat": 9.5910, "lon": 76.5216, "speed": 6.0, "heading": 80, "obstacle": 0},
        {"boat_id": "B02", "lat": 9.5911, "lon": 76.5220, "speed": 5.8, "heading": 80, "obstacle": 0},
    ]


def update(states: list[object], tick: int) -> None:
    if tick > 15:
        states[1].speed = max(0.0, states[1].speed - 0.8)

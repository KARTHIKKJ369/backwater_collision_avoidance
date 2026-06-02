from __future__ import annotations


def make_states() -> list[dict[str, float | int | str]]:
    return [
        {"boat_id": "B01", "lat": 9.5910, "lon": 76.5211, "speed": 8.0, "heading": 90, "obstacle": 0},
        {"boat_id": "B02", "lat": 9.5910, "lon": 76.5240, "speed": 8.0, "heading": 270, "obstacle": 0},
    ]


def update(states: list[object], tick: int) -> None:
    for state in states:
        state.speed = max(4.0, state.speed - 0.01 * tick)

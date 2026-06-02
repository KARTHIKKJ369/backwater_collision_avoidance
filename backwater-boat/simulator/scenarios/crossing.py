from __future__ import annotations


def make_states() -> list[dict[str, float | int | str]]:
    return [
        {"boat_id": "B01", "lat": 9.5910, "lon": 76.5214, "speed": 4.6, "heading": 85, "obstacle": 0},
        {"boat_id": "B02", "lat": 9.5904, "lon": 76.5228, "speed": 4.4, "heading": 350, "obstacle": 0},
    ]


def update(states: list[object], tick: int) -> None:
    if tick > 30:
        states[1].heading -= 0.4

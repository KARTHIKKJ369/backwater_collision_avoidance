from __future__ import annotations


def make_states() -> list[dict[str, float | int | str]]:
    return [
        {"boat_id": "B01", "lat": 9.5907, "lon": 76.5211, "speed": 3.8, "heading": 30, "obstacle": 1},
        {"boat_id": "B02", "lat": 9.5919, "lon": 76.5220, "speed": 3.5, "heading": 215, "obstacle": 1},
    ]


def update(states: list[object], tick: int) -> None:
    states[0].heading += 1.4
    states[1].heading -= 1.2

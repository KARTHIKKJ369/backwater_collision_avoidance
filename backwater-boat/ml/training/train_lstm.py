from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

try:
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.models import Sequential
except ImportError as exc:
    raise SystemExit("Install ML dependencies first: pip install tensorflow numpy") from exc

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "synthetic_trajectories.csv"
MODEL_PATH = Path(__file__).resolve().parents[1] / "model.h5"
WINDOW_SIZE = 10
FORECAST_STEPS = 5
FEATURE_COLUMNS = ("lat", "lon", "speed", "heading")


def load_dataset(path: Path) -> dict[tuple[str, str], list[list[float]]]:
    grouped_rows: dict[tuple[str, str], list[list[float]]] = {}
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = (row["scenario"], row["boat_id"])
            grouped_rows.setdefault(key, []).append([float(row[column]) for column in FEATURE_COLUMNS])
    return grouped_rows


def build_windows(grouped_rows: dict[tuple[str, str], list[list[float]]]) -> tuple[np.ndarray, np.ndarray]:
    features: list[np.ndarray] = []
    targets: list[np.ndarray] = []

    for rows in grouped_rows.values():
        values = np.array(rows, dtype=np.float32)
        if len(values) < WINDOW_SIZE + FORECAST_STEPS:
            continue

        for idx in range(0, len(values) - WINDOW_SIZE - FORECAST_STEPS + 1):
            features.append(values[idx : idx + WINDOW_SIZE])
            targets.append(values[idx + WINDOW_SIZE : idx + WINDOW_SIZE + FORECAST_STEPS, :2].reshape(-1))

    return np.array(features, dtype=np.float32), np.array(targets, dtype=np.float32)


def main() -> None:
    if not DATASET_PATH.exists():
        raise SystemExit(f"Dataset missing: run dataset_generator.py first ({DATASET_PATH})")

    grouped_rows = load_dataset(DATASET_PATH)
    x_train, y_train = build_windows(grouped_rows)

    if len(x_train) == 0:
        raise SystemExit("Not enough data to train the model")

    model = Sequential(
        [
            LSTM(64, return_sequences=True, input_shape=(WINDOW_SIZE, 4)),
            Dropout(0.2),
            LSTM(64),
            Dropout(0.2),
            Dense(FORECAST_STEPS * 2),
        ]
    )
    model.compile(optimizer="adam", loss="mse")
    model.fit(x_train, y_train, epochs=20, batch_size=32, validation_split=0.2, shuffle=True)
    model.save(MODEL_PATH)
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()

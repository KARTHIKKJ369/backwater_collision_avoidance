from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import pandas as pd
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.models import Sequential
except ImportError as exc:
    raise SystemExit("Install ML dependencies first: pip install tensorflow pandas scikit-learn") from exc

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "synthetic_trajectories.csv"
MODEL_PATH = Path(__file__).resolve().parents[1] / "model.h5"


def build_windows(df: "pd.DataFrame") -> tuple[np.ndarray, np.ndarray]:
    features: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    for _, group in df.groupby(["scenario", "boat_id"]):
        values = group[["lat", "lon", "speed", "heading"]].to_numpy(dtype=np.float32)
        for idx in range(0, len(values) - 15):
            features.append(values[idx : idx + 10])
            targets.append(values[idx + 10 : idx + 15, :2])
    return np.array(features), np.array(targets)


def main() -> None:
    if not DATASET_PATH.exists():
        raise SystemExit(f"Dataset missing: run dataset_generator.py first ({DATASET_PATH})")

    df = pd.read_csv(DATASET_PATH)
    x_train, y_train = build_windows(df)

    model = Sequential(
        [
            LSTM(64, return_sequences=True, input_shape=(10, 4)),
            Dropout(0.2),
            LSTM(64),
            Dropout(0.2),
            Dense(10),
        ]
    )
    model.compile(optimizer="adam", loss="mse")
    model.fit(x_train, y_train.reshape((y_train.shape[0], 10)), epochs=20, batch_size=32, validation_split=0.2)
    model.save(MODEL_PATH)
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()

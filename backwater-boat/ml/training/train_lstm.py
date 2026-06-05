from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

try:
    import tensorflow as tf
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
except ImportError as exc:
    raise SystemExit("Install ML dependencies first: pip install tensorflow numpy") from exc

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "synthetic_trajectories.csv"
MODEL_DIR    = Path(__file__).resolve().parents[1]
MODEL_H5     = MODEL_DIR / "model.h5"
MODEL_TFLITE = MODEL_DIR / "model.tflite"
NORM_PATH    = MODEL_DIR / "norm_params.json"

WINDOW_SIZE    = 10
FORECAST_STEPS = 15
FEATURE_COLS   = ("lat", "lon", "speed", "heading")


# ------------------------------------------------------------------
# 1. Load & group
# ------------------------------------------------------------------

def load_dataset(path: Path) -> dict[tuple[str, str], list[list[float]]]:
    grouped: dict[tuple[str, str], list[list[float]]] = {}
    with path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["scenario"], row["boat_id"])
            grouped.setdefault(key, []).append(
                [float(row[c]) for c in FEATURE_COLS]
            )
    return grouped


# ------------------------------------------------------------------
# 2. Normalise
#    lat/lon  → zero-mean, unit-std (computed across training set)
#    speed    → divide by 10  (typical max ~8 m/s, leaves headroom)
#    heading  → sin/cos encoding → 2 channels instead of raw degrees
#    Output shape per step: [lat_n, lon_n, speed_n, sin_h, cos_h] = 5
# ------------------------------------------------------------------

def encode_features(rows: np.ndarray, lat_mu: float, lat_sd: float,
                    lon_mu: float, lon_sd: float) -> np.ndarray:
    lat   = (rows[:, 0] - lat_mu) / lat_sd
    lon   = (rows[:, 1] - lon_mu) / lon_sd
    spd   = rows[:, 2] / 10.0
    h_rad = np.radians(rows[:, 3])
    return np.stack([lat, lon, spd, np.sin(h_rad), np.cos(h_rad)], axis=1)


def compute_norm(grouped: dict) -> tuple[float, float, float, float]:
    all_rows = np.concatenate([np.array(v) for v in grouped.values()])
    return (float(all_rows[:,0].mean()), float(all_rows[:,0].std()),
            float(all_rows[:,1].mean()), float(all_rows[:,1].std()))


def build_windows(grouped: dict, lat_mu: float, lat_sd: float,
                  lon_mu: float, lon_sd: float) -> tuple[np.ndarray, np.ndarray]:
    X, Y = [], []
    for rows_raw in grouped.values():
        arr = np.array(rows_raw, dtype=np.float32)
        enc = encode_features(arr, lat_mu, lat_sd, lon_mu, lon_sd)
        n   = len(enc)
        if n < WINDOW_SIZE + FORECAST_STEPS:
            continue
        for i in range(n - WINDOW_SIZE - FORECAST_STEPS + 1):
            X.append(enc[i : i + WINDOW_SIZE])
            # target = normalised lat/lon only (5 pairs → 10 values)
            tgt_raw = arr[i + WINDOW_SIZE : i + WINDOW_SIZE + FORECAST_STEPS, :2]
            tgt_lat = (tgt_raw[:, 0] - lat_mu) / lat_sd
            tgt_lon = (tgt_raw[:, 1] - lon_mu) / lon_sd
            Y.append(np.stack([tgt_lat, tgt_lon], axis=1).reshape(-1))
    return np.array(X, dtype=np.float32), np.array(Y, dtype=np.float32)


# ------------------------------------------------------------------
# 3. Model
# ------------------------------------------------------------------

INPUT_FEATURES = 5  # lat_n, lon_n, speed_n, sin_h, cos_h

def build_model() -> tf.keras.Model:
    model = Sequential([
        LSTM(128, return_sequences=True, unroll=True,
             input_shape=(WINDOW_SIZE, INPUT_FEATURES)),
        Dropout(0.2),
        LSTM(64, unroll=True),
        Dropout(0.2),
        
        Dense(FORECAST_STEPS * 2),
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="mse",
                  metrics=["mae"])
    return model


# ------------------------------------------------------------------
# 4. TFLite conversion
# ------------------------------------------------------------------

def convert_tflite(model: tf.keras.Model, out_path: Path) -> None:
    conv = tf.lite.TFLiteConverter.from_keras_model(model)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    
    # Force conversion to purely standard TFLite built-in operations
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS]
    
    tflite_model = conv.convert()
    out_path.write_bytes(tflite_model)
    
    kb = len(tflite_model) / 1024
    print(f"  Saved TFLite model  → {out_path}  ({kb:.1f} KB)")


# ------------------------------------------------------------------
# 5. Main
# ------------------------------------------------------------------

def main() -> None:
    if not DATASET_PATH.exists():
        raise SystemExit(
            f"Dataset missing — run dataset_generator.py first:\n"
            f"  python ml/training/dataset_generator.py"
        )

    print("Loading dataset …")
    grouped = load_dataset(DATASET_PATH)
    lat_mu, lat_sd, lon_mu, lon_sd = compute_norm(grouped)
    print(f"  Norm params  lat μ={lat_mu:.6f} σ={lat_sd:.6f}  "
          f"lon μ={lon_mu:.6f} σ={lon_sd:.6f}")

    # Persist norm params so predict.py can denormalise at inference time
    norm = {"lat_mu": lat_mu, "lat_sd": lat_sd,
            "lon_mu": lon_mu, "lon_sd": lon_sd}
    NORM_PATH.write_text(json.dumps(norm, indent=2))
    print(f"  Saved norm params   → {NORM_PATH}")

    print("Building windows …")
    X, Y = build_windows(grouped, lat_mu, lat_sd, lon_mu, lon_sd)
    print(f"  Windows: {len(X)}  input shape: {X.shape}  target shape: {Y.shape}")

    if len(X) == 0:
        raise SystemExit("Not enough data to build training windows.")

    model = build_model()
    model.summary()

    callbacks = [
        EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True,
                      verbose=1),
        ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3,
                          min_lr=1e-5, verbose=1),
    ]

    print("\nTraining …")
    model.fit(X, Y, epochs=60, batch_size=64, validation_split=0.15,
              shuffle=True, callbacks=callbacks)

    model.save(MODEL_H5)
    print(f"\n  Saved Keras model   → {MODEL_H5}")

    print("\nConverting to TFLite …")
    convert_tflite(model, MODEL_TFLITE)

    print("\nDone. Files produced:")
    print(f"  {MODEL_H5}")
    print(f"  {MODEL_TFLITE}")
    print(f"  {NORM_PATH}")
    print("\nNext step: copy model.tflite and norm_params.json to the Pi,")
    print("then update ml/inference/predict.py (already done if you took the full patch).")


if __name__ == "__main__":
    main()

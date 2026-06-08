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
FEATURE_COLS   = ("lat", "lon", "speed", "heading", "ax", "ay", "az", "gx", "gy", "gz")


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
#    lat/lon   → zero-mean, unit-std (computed across training set)
#    speed     → divide by 10  (typical max ~8 m/s, leaves headroom)
#    heading   → sin/cos encoding → 2 channels instead of raw degrees
#    ax/ay/az  → zero-mean, unit-std
#    gx/gy/gz  → zero-mean, unit-std
#    Output shape per step:
#      [lat_n, lon_n, spd_n, sin_h, cos_h, ax_n, ay_n, az_n, gx_n, gy_n, gz_n] = 11
# ------------------------------------------------------------------

def encode_features(rows: np.ndarray, norm: dict) -> np.ndarray:
    # cols: lat lon speed heading ax ay az gx gy gz  (indices 0-9)
    lat   = (rows[:, 0] - norm["lat_mu"]) / norm["lat_sd"]
    lon   = (rows[:, 1] - norm["lon_mu"]) / norm["lon_sd"]
    spd   = rows[:, 2] / 10.0
    h_rad = np.radians(rows[:, 3])
    ax_n  = (rows[:, 4] - norm["ax_mu"])  / norm["ax_sd"]
    ay_n  = (rows[:, 5] - norm["ay_mu"])  / norm["ay_sd"]
    az_n  = (rows[:, 6] - norm["az_mu"])  / norm["az_sd"]
    gx_n  = (rows[:, 7] - norm["gx_mu"])  / norm["gx_sd"]
    gy_n  = (rows[:, 8] - norm["gy_mu"])  / norm["gy_sd"]
    gz_n  = (rows[:, 9] - norm["gz_mu"])  / norm["gz_sd"]
    return np.stack(
        [lat, lon, spd, np.sin(h_rad), np.cos(h_rad),
         ax_n, ay_n, az_n, gx_n, gy_n, gz_n],
        axis=1,
    )


def compute_norm(grouped: dict) -> dict:
    all_rows = np.concatenate([np.array(v) for v in grouped.values()])
    # cols: 0=lat 1=lon 2=speed 3=heading 4=ax 5=ay 6=az 7=gx 8=gy 9=gz
    def _ms(col: int) -> tuple[float, float]:
        mu = float(all_rows[:, col].mean())
        sd = float(all_rows[:, col].std())
        sd = sd if sd > 1e-9 else 1.0   # guard zero-std (flat channels)
        return mu, sd

    lat_mu, lat_sd = _ms(0)
    lon_mu, lon_sd = _ms(1)
    ax_mu,  ax_sd  = _ms(4)
    ay_mu,  ay_sd  = _ms(5)
    az_mu,  az_sd  = _ms(6)
    gx_mu,  gx_sd  = _ms(7)
    gy_mu,  gy_sd  = _ms(8)
    gz_mu,  gz_sd  = _ms(9)

    return dict(
        lat_mu=lat_mu, lat_sd=lat_sd,
        lon_mu=lon_mu, lon_sd=lon_sd,
        ax_mu=ax_mu,   ax_sd=ax_sd,
        ay_mu=ay_mu,   ay_sd=ay_sd,
        az_mu=az_mu,   az_sd=az_sd,
        gx_mu=gx_mu,   gx_sd=gx_sd,
        gy_mu=gy_mu,   gy_sd=gy_sd,
        gz_mu=gz_mu,   gz_sd=gz_sd,
    )


def build_windows(grouped: dict, norm: dict) -> tuple[np.ndarray, np.ndarray]:
    X, Y = [], []
    lat_mu, lat_sd = norm["lat_mu"], norm["lat_sd"]
    lon_mu, lon_sd = norm["lon_mu"], norm["lon_sd"]
    for rows_raw in grouped.values():
        arr = np.array(rows_raw, dtype=np.float32)
        enc = encode_features(arr, norm)
        n   = len(enc)
        if n < WINDOW_SIZE + FORECAST_STEPS:
            continue
        for i in range(n - WINDOW_SIZE - FORECAST_STEPS + 1):
            X.append(enc[i : i + WINDOW_SIZE])
            # target = DELTA from last window position (normalised)
            # This makes training translation-invariant — model learns dynamics
            # not geography, so deployment lat/lon mismatch no longer OOD.
            origin_lat = arr[i + WINDOW_SIZE - 1, 0]
            origin_lon = arr[i + WINDOW_SIZE - 1, 1]
            tgt_raw = arr[i + WINDOW_SIZE : i + WINDOW_SIZE + FORECAST_STEPS, :2]
            tgt_dlat = (tgt_raw[:, 0] - origin_lat) / lat_sd
            tgt_dlon = (tgt_raw[:, 1] - origin_lon) / lon_sd
            Y.append(np.stack([tgt_dlat, tgt_dlon], axis=1).reshape(-1))
    return np.array(X, dtype=np.float32), np.array(Y, dtype=np.float32)


# ------------------------------------------------------------------
# 3. Model
# ------------------------------------------------------------------

INPUT_FEATURES = 11  # lat_n, lon_n, spd_n, sin_h, cos_h, ax_n, ay_n, az_n, gx_n, gy_n, gz_n

def build_model() -> tf.keras.Model:
    model = Sequential([
        LSTM(128, return_sequences=True,
             input_shape=(WINDOW_SIZE, INPUT_FEATURES)),
        Dropout(0.2),
        LSTM(64),
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
    # Rebuild with unroll=True for TFLite compatibility, copy weights
    tflite_model_def = Sequential([
        LSTM(128, return_sequences=True, unroll=True,
             input_shape=(WINDOW_SIZE, INPUT_FEATURES)),
        Dropout(0.2),
        LSTM(64, unroll=True),
        Dropout(0.2),
        Dense(FORECAST_STEPS * 2),
    ])
    tflite_model_def.set_weights(model.get_weights())

    conv = tf.lite.TFLiteConverter.from_keras_model(tflite_model_def)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS]
    tflite_bytes = conv.convert()
    out_path.write_bytes(tflite_bytes)
    print(f"  Saved TFLite model  → {out_path}  ({len(tflite_bytes)/1024:.1f} KB)")


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
    norm = compute_norm(grouped)
    print(f"  Norm params  lat μ={norm['lat_mu']:.6f} σ={norm['lat_sd']:.6f}  "
          f"lon μ={norm['lon_mu']:.6f} σ={norm['lon_sd']:.6f}")
    print(f"               ax  μ={norm['ax_mu']:.4f}  σ={norm['ax_sd']:.4f}  "
          f"gz  μ={norm['gz_mu']:.4f}  σ={norm['gz_sd']:.4f}")

    # Persist norm params so predict.py can denormalise at inference time
    NORM_PATH.write_text(json.dumps(norm, indent=2))
    print(f"  Saved norm params   → {NORM_PATH}")

    print("Building windows …")
    X, Y = build_windows(grouped, norm)
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
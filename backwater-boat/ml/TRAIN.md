# Training & deployment guide

## Prerequisites (laptop)
```
pip install tensorflow==2.16.2 numpy==1.26.4
```

## Step 1 — train
Run from the repo root:
```
python ml/training/train_lstm.py
```
Produces three files in `ml/`:
- `model.h5`          — Keras model (dev/reference)
- `model.tflite`      — quantised TFLite model (Pi)
- `norm_params.json`  — normalisation params (required at inference time)

Training takes ~2–5 min on a modern laptop CPU; faster on GPU.
Early stopping fires around epoch 20–35 typically.

## Step 2 — verify locally
```python
from ml.inference.predict import predict_future_positions
history = [
    {"lat": 9.591, "lon": 76.522, "speed": 4.2, "heading": 65}
] * 10
print(predict_future_positions(history))
```
You should see 5 dicts with `lat`, `lon`, `confidence` — and confidence
values that vary (not all 0.99), which confirms the model is running
rather than dead-reckoning.

## Step 3 — copy to Pi
```
scp ml/model.tflite ml/norm_params.json pi@192.168.4.1:~/backwater-boat/ml/
```
Only these two files are needed on the Pi. Do NOT copy model.h5
(it requires full TensorFlow which is too heavy for Pi).

## Step 4 — Pi install
```
pip install tflite-runtime numpy==1.26.4 --break-system-packages
```

## What changed in predict.py
- Resolution order: TFLite → Keras → dead-reckoning
- Features are now normalised (lat/lon zero-mean, heading → sin/cos)
- `norm_params.json` must exist alongside the model files
- Input shape: (1, 10, 5) — 5 features, not 4

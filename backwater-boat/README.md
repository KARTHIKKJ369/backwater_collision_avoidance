# IoT-Based Intelligent Backwater Boat Collision Avoidance System

Software-first prototype for predictive maritime collision avoidance using simulated boat telemetry, MQTT, FastAPI, SQLite, risk scoring, LSTM trajectory prediction, and a React Leaflet dashboard.

## Architecture

```text
Virtual Sensors / Real Sensors
(GPS + IMU + Camera + LoRa)
            ↓
ESP32
            ↓
LoRa
            ↓
LoRa → MQTT Bridge
            ↓
Mosquitto MQTT Broker
            ↓
Backend API
            ↓
SQLite Database
            ↓
Risk Engine
            ↓
LSTM Prediction (Raspberry Pi)
            ↓
Dashboard
```

## Quick Start

```bash
docker compose up --build
```

If `docker compose up --build` prints `unknown flag: --build`, Docker Compose is not installed or not connected to your Docker CLI. On Arch Linux:

```bash
sudo pacman -S docker-compose
docker compose version
docker compose up --build
```

If your installation exposes the older standalone command instead, use:

```bash
docker-compose up --build
```

Services:

- Dashboard: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- MQTT broker: localhost:1883

Expected flow:

```text
Simulator → MQTT → Backend → SQLite → Risk Engine → LSTM → Dashboard
```

## Local Development

Backend:

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=.. uvicorn backend.api.main:app --reload
```

Simulator:

```bash
cd simulator
pip install -r requirements.txt
MQTT_HOST=localhost python boat_sim.py --scenario crossing
```

Dashboard:

```bash
cd dashboard
npm install
npm run dev
```

ML training:

```bash
pip install -r ml/requirements.txt
python ml/training/dataset_generator.py
python ml/training/train_lstm.py
```

## Scenarios

The simulator supports:

- `straight`
- `crossing`
- `blind_turn`
- `collision`
- `HEAD_ON`
- `sudden_stop`

Example:

```bash
python simulator/boat_sim.py --scenario HEAD_ON
```

## Predictive Collision Upgrade

Alerts are generated from predicted future separation instead of repeated distance-only checks:

```text
Telemetry → Trigger Gate → LSTM/Dead-Reckoning Prediction → Future Collision Check → Alert State Machine
```

Prediction only runs when the current distance is under 150 meters or risk is above 0.3. Alerts are saved only when the pair state changes between `SAFE`, `WARNING`, and `DANGER`, with a 10 second cooldown.

## Cooperative Avoidance

The backend now publishes maneuver recommendations on `boats/{id}/recommendation` and listens for acknowledgements on `boats/{id}/ack`.

Recommendation payload:

```json
{
  "action": "TURN_RIGHT",
  "accepted": true
}
```

## Tests

```bash
PYTHONPATH=. python -m unittest discover backend/tests
```

## Evaluation

The backend exposes evaluation metrics and writes `results/evaluation.csv` and `results/summary.json`:
The backend exposes evaluation metrics and writes `results/evaluation.csv`, `results/{scenario}.csv`, and `results/summary.json`:

```bash
curl http://localhost:8000/evaluation
curl http://localhost:8000/timeline?scenario=HEAD_ON
```

Run all automated scenarios after the stack is up:

```bash
cd simulator
API_BASE=http://localhost:8000 MQTT_HOST=localhost python run_scenarios.py
```

## Team Split

- Member 1: ESP32 and LoRa packet protocol.
- Member 2: MQTT bridge and backend ingestion.
- Member 3: Risk engine and SQLite persistence.
- Member 4: LSTM dataset, training, and inference.
- Member 5: React dashboard and integration testing.

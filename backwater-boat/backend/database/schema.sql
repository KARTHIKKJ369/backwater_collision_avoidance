CREATE TABLE IF NOT EXISTS boats (
    boat_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boat_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    speed REAL NOT NULL,
    heading REAL NOT NULL,
    obstacle INTEGER NOT NULL DEFAULT 0,
    risk REAL NOT NULL DEFAULT 0,
    scenario TEXT NOT NULL DEFAULT 'LIVE',
    FOREIGN KEY (boat_id) REFERENCES boats (boat_id)
);

CREATE TABLE IF NOT EXISTS prediction (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boat_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    pred_lat REAL NOT NULL,
    pred_lon REAL NOT NULL,
    confidence REAL NOT NULL,
    scenario TEXT NOT NULL DEFAULT 'LIVE',
    FOREIGN KEY (boat_id) REFERENCES boats (boat_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boat_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    scenario TEXT NOT NULL DEFAULT 'LIVE',
    FOREIGN KEY (boat_id) REFERENCES boats (boat_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boat_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    action TEXT NOT NULL,
    accepted INTEGER NOT NULL DEFAULT 0,
    scenario TEXT NOT NULL DEFAULT 'LIVE',
    alert_state TEXT NOT NULL DEFAULT 'SAFE',
    FOREIGN KEY (boat_id) REFERENCES boats (boat_id)
);

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("SQLITE_PATH", BASE_DIR / "data" / "boats.db"))
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _ensure_column(conn, "telemetry", "scenario", "TEXT NOT NULL DEFAULT 'LIVE'")
        _ensure_column(conn, "prediction", "scenario", "TEXT NOT NULL DEFAULT 'LIVE'")
        _ensure_column(conn, "alerts", "scenario", "TEXT NOT NULL DEFAULT 'LIVE'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                boat_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                action TEXT NOT NULL,
                accepted INTEGER NOT NULL DEFAULT 0,
                scenario TEXT NOT NULL DEFAULT 'LIVE',
                alert_state TEXT NOT NULL DEFAULT 'SAFE',
                FOREIGN KEY (boat_id) REFERENCES boats (boat_id)
            )
            """
        )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def upsert_boat(boat_id: str, name: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO boats (boat_id, name)
            VALUES (?, ?)
            ON CONFLICT(boat_id) DO UPDATE SET name = excluded.name
            """,
            (boat_id, name or f"Boat {boat_id}"),
        )


def insert_telemetry(payload: dict[str, Any], risk: float = 0.0) -> int:
    upsert_boat(payload["boat_id"])
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO telemetry
                (boat_id, timestamp, lat, lon, speed, heading, obstacle, risk, scenario)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["boat_id"],
                payload["timestamp"],
                payload["lat"],
                payload["lon"],
                payload["speed"],
                payload["heading"],
                int(payload.get("obstacle", 0)),
                risk,
                payload.get("scenario", "LIVE"),
            ),
        )
        return int(cur.lastrowid)


def insert_prediction(
    boat_id: str,
    timestamp: float,
    pred_lat: float,
    pred_lon: float,
    confidence: float,
    scenario: str = "LIVE",
) -> int:
    upsert_boat(boat_id)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO prediction (boat_id, timestamp, pred_lat, pred_lon, confidence, scenario)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (boat_id, timestamp, pred_lat, pred_lon, confidence, scenario),
        )
        return int(cur.lastrowid)


def insert_alert(boat_id: str, timestamp: float, severity: str, message: str, scenario: str = "LIVE") -> int:
    upsert_boat(boat_id)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO alerts (boat_id, timestamp, severity, message, scenario)
            VALUES (?, ?, ?, ?, ?)
            """,
            (boat_id, timestamp, severity, message, scenario),
        )
        return int(cur.lastrowid)


def insert_recommendation(
    boat_id: str,
    timestamp: float,
    action: str,
    scenario: str = "LIVE",
    alert_state: str = "SAFE",
    accepted: bool = False,
) -> int:
    upsert_boat(boat_id)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO recommendations (boat_id, timestamp, action, accepted, scenario, alert_state)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (boat_id, timestamp, action, int(accepted), scenario, alert_state),
        )
        return int(cur.lastrowid)


def mark_recommendation_accepted(boat_id: str, action: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM recommendations
            WHERE boat_id = ? AND action = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (boat_id, action),
        ).fetchone()
        if not row:
            return 0
        conn.execute("UPDATE recommendations SET accepted = 1 WHERE id = ?", (row["id"],))
        return int(row["id"])


def fetch_all(table: str, limit: int = 200) -> list[dict[str, Any]]:
    allowed = {"boats", "telemetry", "prediction", "alerts", "recommendations"}
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return rows_to_dicts(rows)


def count_rows(table: str) -> int:
    allowed = {"boats", "telemetry", "prediction", "alerts", "recommendations"}
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    with get_connection() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])


def average_risk(scenario: str | None = None) -> float:
    with get_connection() as conn:
        if scenario:
            row = conn.execute("SELECT AVG(risk) AS avg_risk FROM telemetry WHERE scenario = ?", (scenario,)).fetchone()
        else:
            row = conn.execute("SELECT AVG(risk) AS avg_risk FROM telemetry").fetchone()
        return round(float(row["avg_risk"] or 0), 3)


def latest_telemetry(limit: int = 50) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT t.*
            FROM telemetry t
            INNER JOIN (
                SELECT boat_id, MAX(id) AS max_id FROM telemetry GROUP BY boat_id
            ) latest ON latest.max_id = t.id
            ORDER BY t.boat_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return rows_to_dicts(rows)


def fetch_by_scenario(table: str, scenario: str, limit: int = 10_000) -> list[dict[str, Any]]:
    allowed = {"telemetry", "prediction", "alerts", "recommendations"}
    if table not in allowed:
        raise ValueError(f"Unsupported scenario table: {table}")
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE scenario = ? ORDER BY rowid DESC LIMIT ?",
            (scenario, limit),
        ).fetchall()
        return rows_to_dicts(rows)


def telemetry_for_boat(boat_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM telemetry
            WHERE boat_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (boat_id, limit),
        ).fetchall()
        return list(reversed(rows_to_dicts(rows)))


def telemetry_after(boat_id: str, timestamp: float, limit: int = 5) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM telemetry
            WHERE boat_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC, id ASC
            LIMIT ?
            """,
            (boat_id, timestamp, limit),
        ).fetchall()
        return rows_to_dicts(rows)

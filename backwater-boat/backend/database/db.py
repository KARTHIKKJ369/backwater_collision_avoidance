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
                (boat_id, timestamp, lat, lon, speed, heading, obstacle, risk)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        return int(cur.lastrowid)


def insert_prediction(boat_id: str, timestamp: float, pred_lat: float, pred_lon: float, confidence: float) -> int:
    upsert_boat(boat_id)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO prediction (boat_id, timestamp, pred_lat, pred_lon, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (boat_id, timestamp, pred_lat, pred_lon, confidence),
        )
        return int(cur.lastrowid)


def insert_alert(boat_id: str, timestamp: float, severity: str, message: str) -> int:
    upsert_boat(boat_id)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO alerts (boat_id, timestamp, severity, message)
            VALUES (?, ?, ?, ?)
            """,
            (boat_id, timestamp, severity, message),
        )
        return int(cur.lastrowid)


def fetch_all(table: str, limit: int = 200) -> list[dict[str, Any]]:
    allowed = {"boats", "telemetry", "prediction", "alerts"}
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    with get_connection() as conn:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return rows_to_dicts(rows)


def count_rows(table: str) -> int:
    allowed = {"boats", "telemetry", "prediction", "alerts"}
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    with get_connection() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])


def average_risk() -> float:
    with get_connection() as conn:
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

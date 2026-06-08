from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("SQLITE_PATH", BASE_DIR / "data" / "boats.db"))
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# ── connection pool ──────────────────────────────────────────────────────────
# SQLite in WAL mode supports one writer + many readers concurrently, but each
# thread must use its own connection (check_same_thread=False is not enough
# when connections share a write transaction).  We keep one connection per
# thread via threading.local so the pool is bounded by uvicorn's thread count.

_local = threading.local()
_db_ready = False          # set to True after the first init_db() call
_init_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        DB_PATH,
        timeout=15,            # wait up to 15 s for a write lock before raising
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    # WAL mode: readers never block writers, writers never block readers
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")   # safe with WAL; faster than FULL
    conn.execute("PRAGMA busy_timeout=15000")   # ms — belt-and-suspenders
    return conn


def get_connection() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _connect()
    return _local.conn


def init_db() -> None:
    """
    Create tables and run migrations.  Safe to call multiple times — after the
    first successful run it short-circuits so repeated calls from _rows() or
    startup hooks are free.
    """
    global _db_ready
    if _db_ready:
        return
    with _init_lock:
        if _db_ready:          # double-checked locking
            return
        conn = get_connection()
        # executescript commits any open transaction and runs DDL; fine here
        # because this only runs once at startup.
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _ensure_column(conn, "telemetry",        "scenario", "TEXT NOT NULL DEFAULT 'LIVE'")
        _ensure_column(conn, "prediction",       "scenario", "TEXT NOT NULL DEFAULT 'LIVE'")
        _ensure_column(conn, "alerts",           "scenario", "TEXT NOT NULL DEFAULT 'LIVE'")
        _ensure_column(conn, "recommendations",  "scenario", "TEXT NOT NULL DEFAULT 'LIVE'")
        _ensure_column(conn, "recommendations",  "alert_state", "TEXT NOT NULL DEFAULT 'SAFE'")
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
        conn.commit()
        _db_ready = True


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


# ── helpers ──────────────────────────────────────────────────────────────────

def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


# ── write operations ─────────────────────────────────────────────────────────

def upsert_boat(boat_id: str, name: str | None = None) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO boats (boat_id, name)
        VALUES (?, ?)
        ON CONFLICT(boat_id) DO UPDATE SET name = excluded.name
        """,
        (boat_id, name or f"Boat {boat_id}"),
    )
    conn.commit()


def insert_telemetry(payload: dict[str, Any], risk: float = 0.0) -> int:
    upsert_boat(payload["boat_id"])
    conn = get_connection()
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
    conn.commit()
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
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO prediction (boat_id, timestamp, pred_lat, pred_lon, confidence, scenario)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (boat_id, timestamp, pred_lat, pred_lon, confidence, scenario),
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_alert(boat_id: str, timestamp: float, severity: str, message: str, scenario: str = "LIVE") -> int:
    upsert_boat(boat_id)
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO alerts (boat_id, timestamp, severity, message, scenario)
        VALUES (?, ?, ?, ?, ?)
        """,
        (boat_id, timestamp, severity, message, scenario),
    )
    conn.commit()
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
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO recommendations (boat_id, timestamp, action, accepted, scenario, alert_state)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (boat_id, timestamp, action, int(accepted), scenario, alert_state),
    )
    conn.commit()
    return int(cur.lastrowid)


def mark_recommendation_accepted(boat_id: str, action: str) -> int:
    conn = get_connection()
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
    conn.commit()
    return int(row["id"])


# ── read operations ───────────────────────────────────────────────────────────

def fetch_all(table: str, limit: int = 200) -> list[dict[str, Any]]:
    allowed = {"boats", "telemetry", "prediction", "alerts", "recommendations"}
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    conn = get_connection()
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
    return rows_to_dicts(rows)


def count_rows(table: str) -> int:
    allowed = {"boats", "telemetry", "prediction", "alerts", "recommendations"}
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    conn = get_connection()
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"])


def count_prediction_runs() -> int:
    """Count distinct prediction events (not individual lat/lon points).

    Each call to run_prediction() inserts up to FORECAST_STEPS (5–10) rows
    all sharing the same (boat_id, timestamp) pair.  Counting rows directly
    inflates the figure by that factor.  This query counts unique events.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM (SELECT 1 FROM prediction GROUP BY boat_id, timestamp)"
    ).fetchone()
    return int(row["count"])


def average_risk(scenario: str | None = None) -> float:
    conn = get_connection()
    if scenario:
        row = conn.execute("SELECT AVG(risk) AS avg_risk FROM telemetry WHERE scenario = ?", (scenario,)).fetchone()
    else:
        row = conn.execute("SELECT AVG(risk) AS avg_risk FROM telemetry").fetchone()
    return round(float(row["avg_risk"] or 0), 3)


def latest_telemetry(limit: int = 50) -> list[dict[str, Any]]:
    conn = get_connection()
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


def latest_predictions() -> list[dict[str, Any]]:
    """Return only the most-recent prediction batch per boat.

    Each prediction run inserts FORECAST_STEPS rows all sharing the same
    (boat_id, timestamp).  fetch_all() returns the N most-recent rows by
    rowid, which mixes batches from multiple ticks and produces the fan of
    lines on the map.  This query keeps only the rows whose timestamp equals
    the MAX timestamp for each boat, giving a single clean trajectory.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT p.*
        FROM prediction p
        INNER JOIN (
            SELECT boat_id, MAX(timestamp) AS max_ts
            FROM prediction
            GROUP BY boat_id
        ) latest ON latest.boat_id = p.boat_id
                 AND latest.max_ts  = p.timestamp
        ORDER BY p.boat_id, p.rowid
        """
    ).fetchall()
    return rows_to_dicts(rows)


def fetch_by_scenario(table: str, scenario: str, limit: int = 10_000) -> list[dict[str, Any]]:
    allowed = {"telemetry", "prediction", "alerts", "recommendations"}
    if table not in allowed:
        raise ValueError(f"Unsupported scenario table: {table}")
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE scenario = ? ORDER BY rowid DESC LIMIT ?",
        (scenario, limit),
    ).fetchall()
    return rows_to_dicts(rows)


def telemetry_for_boat(boat_id: str, limit: int = 20) -> list[dict[str, Any]]:
    conn = get_connection()
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
    conn = get_connection()
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
"""SQLite layer for pool temp readings + outdoor weather cache."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pool_readings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT    NOT NULL,
    temp_f     REAL    NOT NULL,
    remote_ip  TEXT,
    raw_json   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS pool_sensor_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_id  INTEGER NOT NULL,
    addr        TEXT    NOT NULL,
    temp_f      REAL    NOT NULL,
    FOREIGN KEY (reading_id) REFERENCES pool_readings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS outdoor_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    station_id  TEXT,
    temp_f      REAL    NOT NULL,
    raw_json    TEXT
);

CREATE INDEX IF NOT EXISTS idx_pool_readings_ts    ON pool_readings(ts);
CREATE INDEX IF NOT EXISTS idx_outdoor_readings_ts ON outdoor_readings(ts);
CREATE INDEX IF NOT EXISTS idx_sensor_reading_id   ON pool_sensor_readings(reading_id);

CREATE TABLE IF NOT EXISTS hourly_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    water_f       REAL,
    water_age_s   INTEGER,
    water_source  TEXT,
    air_550_f     REAL,
    air_264_f     REAL,
    error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_hourly_log_ts ON hourly_log(ts);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)


def insert_pool_reading(payload: dict, remote_ip: str | None) -> int:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    temp_f = float(payload.get("temp_f", 0.0))
    raw = json.dumps(payload, separators=(",", ":"))
    with connect() as c:
        cur = c.execute(
            "INSERT INTO pool_readings (ts, temp_f, remote_ip, raw_json) VALUES (?, ?, ?, ?)",
            (ts, temp_f, remote_ip, raw),
        )
        reading_id = cur.lastrowid
        for s in payload.get("sensors") or []:
            c.execute(
                "INSERT INTO pool_sensor_readings (reading_id, addr, temp_f) VALUES (?, ?, ?)",
                (reading_id, str(s.get("addr", "")), float(s.get("temp_f", 0.0))),
            )
    return reading_id


def insert_outdoor_reading(source: str, temp_f: float, station_id: str | None, raw: dict | None) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as c:
        c.execute(
            "INSERT INTO outdoor_readings (ts, source, station_id, temp_f, raw_json) VALUES (?, ?, ?, ?, ?)",
            (ts, source, station_id, temp_f, json.dumps(raw) if raw else None),
        )


def latest_pool_reading() -> dict | None:
    with connect() as c:
        row = c.execute(
            "SELECT id, ts, temp_f, raw_json FROM pool_readings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        sensors = c.execute(
            "SELECT addr, temp_f FROM pool_sensor_readings WHERE reading_id = ?",
            (row["id"],),
        ).fetchall()
    # Pull a few optional metadata fields out of the raw payload so the home
    # page can show "via club site" vs "N sensors" without another query.
    source = label = None
    try:
        raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
        source = raw.get("source")
        label  = raw.get("label")
    except (ValueError, TypeError):
        pass
    return {
        "ts": row["ts"],
        "temp_f": row["temp_f"],
        "sensors": [{"addr": s["addr"], "temp_f": s["temp_f"]} for s in sensors],
        "source": source,
        "label":  label,
    }


def latest_outdoor_reading() -> dict | None:
    with connect() as c:
        row = c.execute(
            "SELECT ts, source, station_id, temp_f FROM outdoor_readings ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def pool_history(since: datetime) -> list[dict]:
    cutoff = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    with connect() as c:
        rows = c.execute(
            "SELECT ts, temp_f FROM pool_readings WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def outdoor_history(since: datetime) -> list[dict]:
    cutoff = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    with connect() as c:
        rows = c.execute(
            "SELECT ts, temp_f, source FROM outdoor_readings WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def range_to_since(range_key: str) -> datetime:
    now = datetime.now(timezone.utc)
    return {
        "24h": now - timedelta(hours=24),
        "7d":  now - timedelta(days=7),
        "30d": now - timedelta(days=30),
        "1y":  now - timedelta(days=365),
        "all": datetime(1970, 1, 1, tzinfo=timezone.utc),
    }.get(range_key, now - timedelta(hours=24))


def insert_hourly_log(
    water_f: float | None,
    water_age_s: int | None,
    water_source: str | None,
    air_550_f: float | None,
    air_264_f: float | None,
    error: str | None,
) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as c:
        c.execute(
            "INSERT INTO hourly_log (ts, water_f, water_age_s, water_source, air_550_f, air_264_f, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, water_f, water_age_s, water_source, air_550_f, air_264_f, error),
        )


def hourly_log(since: datetime) -> list[dict]:
    cutoff = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    with connect() as c:
        rows = c.execute(
            "SELECT ts, water_f, water_age_s, water_source, air_550_f, air_264_f, error "
            "FROM hourly_log WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]

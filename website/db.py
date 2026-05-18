"""SQLite layer for pool temp readings + outdoor weather cache + PWS history."""

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

-- Backfilled history from Weather Underground PWS "history/all" endpoint.
-- One row per (station, observation timestamp). Stores rich payload so we
-- can mine dewpoint/wind/precip later without re-pulling.
CREATE TABLE IF NOT EXISTS pws_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id   TEXT    NOT NULL,
    ts           TEXT    NOT NULL,      -- ISO UTC, second-resolution
    temp_f       REAL,
    dewpt_f      REAL,
    humidity     REAL,
    wind_speed   REAL,
    wind_gust    REAL,
    wind_dir     REAL,
    pressure_in  REAL,
    precip_rate  REAL,
    precip_total REAL,
    solar_rad    REAL,
    uv           REAL,
    raw_json     TEXT,
    UNIQUE(station_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_pws_history_station_ts ON pws_history(station_id, ts);
CREATE INDEX IF NOT EXISTS idx_pws_history_ts         ON pws_history(ts);

-- Backfilled history from NWS for KHSV airport ASOS. Same shape as the live
-- 'outdoor_readings' rows where source='nws', but pre-loaded going back days/weeks.
CREATE TABLE IF NOT EXISTS nws_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id  TEXT    NOT NULL,       -- e.g. 'KHSV'
    ts          TEXT    NOT NULL,
    temp_f      REAL,
    dewpt_f     REAL,
    humidity    REAL,
    wind_speed  REAL,
    pressure_mb REAL,
    raw_json    TEXT,
    UNIQUE(station_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_nws_history_station_ts ON nws_history(station_id, ts);
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
        "90d": now - timedelta(days=90),
        "1y":  now - timedelta(days=365),
        "2y":  now - timedelta(days=730),
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


# ---------------------------------------------------------------- PWS history

def insert_pws_observation(station_id: str, obs: dict) -> None:
    """Insert one PWS observation row from a WU history payload.

    `obs` is one element of the 'observations' list returned by
    /v2/pws/history/all. We pull both the top-level fields and the 'imperial'
    sub-block, since `tempAvg` etc. live inside it."""
    ts = obs.get("obsTimeUtc")
    if not ts:
        return
    imp = obs.get("imperial") or {}
    with connect() as c:
        c.execute(
            "INSERT OR IGNORE INTO pws_history "
            "(station_id, ts, temp_f, dewpt_f, humidity, wind_speed, wind_gust, wind_dir, "
            " pressure_in, precip_rate, precip_total, solar_rad, uv, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                station_id,
                ts,
                imp.get("tempAvg") if imp.get("tempAvg") is not None else imp.get("temp"),
                imp.get("dewptAvg") if imp.get("dewptAvg") is not None else imp.get("dewpt"),
                obs.get("humidityAvg") if obs.get("humidityAvg") is not None else obs.get("humidity"),
                imp.get("windspeedAvg") if imp.get("windspeedAvg") is not None else imp.get("windSpeed"),
                imp.get("windgustHigh") if imp.get("windgustHigh") is not None else imp.get("windGust"),
                obs.get("winddirAvg") if obs.get("winddirAvg") is not None else obs.get("winddir"),
                imp.get("pressureMax") if imp.get("pressureMax") is not None else imp.get("pressure"),
                imp.get("precipRate"),
                imp.get("precipTotal"),
                obs.get("solarRadiationHigh") if obs.get("solarRadiationHigh") is not None else obs.get("solarRadiation"),
                obs.get("uvHigh") if obs.get("uvHigh") is not None else obs.get("uvIndex"),
                json.dumps(obs, separators=(",", ":")),
            ),
        )


def pws_history_range(station_id: str, since: datetime) -> list[dict]:
    cutoff = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    with connect() as c:
        rows = c.execute(
            "SELECT ts, temp_f, dewpt_f, humidity, wind_speed, pressure_in "
            "FROM pws_history WHERE station_id = ? AND ts >= ? ORDER BY ts ASC",
            (station_id, cutoff),
        ).fetchall()
    return [dict(r) for r in rows]


def pws_history_count(station_id: str) -> int:
    with connect() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
            "FROM pws_history WHERE station_id = ?",
            (station_id,),
        ).fetchone()
    return dict(row)


def pws_paired_history(station_a: str, station_b: str, since: datetime) -> list[dict]:
    """Return rows where both stations have an observation at the same ts.
    The two stations report on the same 5-minute boundaries, so an exact ts
    match works for the vast majority of points; mismatches just drop."""
    cutoff = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    with connect() as c:
        rows = c.execute(
            "SELECT a.ts, a.temp_f AS a_temp, b.temp_f AS b_temp, "
            "       a.humidity AS a_hum, b.humidity AS b_hum, "
            "       a.dewpt_f AS a_dew,  b.dewpt_f AS b_dew "
            "FROM pws_history a "
            "JOIN pws_history b ON a.ts = b.ts "
            "WHERE a.station_id = ? AND b.station_id = ? AND a.ts >= ? "
            "ORDER BY a.ts ASC",
            (station_a, station_b, cutoff),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- NWS history

def insert_nws_observation(station_id: str, ts: str, props: dict) -> None:
    with connect() as c:
        tc = (props.get("temperature") or {}).get("value")
        dc = (props.get("dewpoint")    or {}).get("value")
        rh = (props.get("relativeHumidity") or {}).get("value")
        ws = (props.get("windSpeed") or {}).get("value")
        pm = (props.get("seaLevelPressure") or {}).get("value")
        c.execute(
            "INSERT OR IGNORE INTO nws_history "
            "(station_id, ts, temp_f, dewpt_f, humidity, wind_speed, pressure_mb, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                station_id, ts,
                None if tc is None else tc * 9.0 / 5.0 + 32.0,
                None if dc is None else dc * 9.0 / 5.0 + 32.0,
                rh,
                ws,
                None if pm is None else pm / 100.0,
                json.dumps(props, separators=(",", ":")),
            ),
        )


def nws_history_range(station_id: str, since: datetime) -> list[dict]:
    cutoff = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    with connect() as c:
        rows = c.execute(
            "SELECT ts, temp_f, dewpt_f, humidity, wind_speed FROM nws_history "
            "WHERE station_id = ? AND ts >= ? ORDER BY ts ASC",
            (station_id, cutoff),
        ).fetchall()
    return [dict(r) for r in rows]

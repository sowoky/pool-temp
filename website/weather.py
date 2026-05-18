"""Outdoor temperature sources.

Resolves in priority order:
  1. Wunderground PWS (authenticated, if WUNDERGROUND_API_KEY env set)
  2. Wunderground PWS (public, uses the same anonymous key wunderground.com's
                       own dashboard widget uses; no signup required)
  3. OpenWeatherMap   (if OWM_API_KEY env set)
  4. NWS              (always available, no key; defaults to KHSV / Huntsville Intl)

Each `fetch_outdoor` call returns (temp_f, source_name, station_id, raw_response_dict).

Also exposes historical-fetch helpers used by the backfill scripts and by the
forecast/analysis pages.
"""

import os
import re
from datetime import datetime, timezone
from typing import Optional

import requests

DEFAULT_LAT = 34.7304   # Huntsville AL approx
DEFAULT_LON = -86.5861
DEFAULT_NWS_STATION = "KHSV"  # Huntsville International Airport (HSV)

WU_KEY      = os.environ.get("WUNDERGROUND_API_KEY")
WU_STATIONS = [s.strip() for s in os.environ.get(
    "WUNDERGROUND_STATION_IDS", "KALHUNTS560,KALHUNTS264"
).split(",") if s.strip()]
OWM_KEY     = os.environ.get("OWM_API_KEY")

# Public key the wunderground.com dashboard widget uses. No signup; works
# for any public PWS.
PUBLIC_WU_KEY = "e1f10a1e78da46f5b10a1e78da96f525"


# ---------------------------------------------------------------- live fetch

def _try_wunderground() -> Optional[tuple]:
    if not WU_KEY:
        return None
    url = "https://api.weather.com/v2/pws/observations/current"
    for station in WU_STATIONS:
        try:
            r = requests.get(url, params={
                "stationId": station,
                "format":    "json",
                "units":     "e",
                "apiKey":    WU_KEY,
            }, timeout=10)
            r.raise_for_status()
            data = r.json()
            obs = (data.get("observations") or [{}])[0]
            temp_f = obs.get("imperial", {}).get("temp")
            if temp_f is None:
                continue
            return float(temp_f), "wunderground", station, data
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"[weather] wunderground {station} failed: {e}")
            continue
    return None


def _try_wunderground_public() -> Optional[tuple]:
    if not WU_STATIONS:
        return None
    url = "https://api.weather.com/v2/pws/observations/current"
    for station in WU_STATIONS:
        try:
            r = requests.get(
                url,
                params={"stationId": station, "format": "json",
                        "units": "e", "apiKey": PUBLIC_WU_KEY},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            obs = (data.get("observations") or [{}])[0]
            temp_f = obs.get("imperial", {}).get("temp")
            if temp_f is None:
                continue
            return float(temp_f), "wunderground-public", station, data
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"[weather] wunderground-public {station} failed: {e}")
            continue
    return None


def _try_openweather() -> Optional[tuple]:
    if not OWM_KEY:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": DEFAULT_LAT, "lon": DEFAULT_LON, "units": "imperial", "appid": OWM_KEY}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        temp_f = data.get("main", {}).get("temp")
        if temp_f is None:
            return None
        return float(temp_f), "openweather", None, data
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"[weather] openweather failed: {e}")
        return None


def _try_nws() -> Optional[tuple]:
    url = f"https://api.weather.gov/stations/{DEFAULT_NWS_STATION}/observations/latest"
    headers = {
        "User-Agent": "pool-temp-monitor (kyleroden@gmail.com)",
        "Accept":     "application/geo+json",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        temp_c = data.get("properties", {}).get("temperature", {}).get("value")
        if temp_c is None:
            return None
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        return float(temp_f), "nws", DEFAULT_NWS_STATION, data
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"[weather] nws failed: {e}")
        return None


def fetch_outdoor() -> Optional[tuple]:
    """Returns (temp_f, source, station_id, raw_json) or None if all sources fail."""
    for src in (_try_wunderground, _try_wunderground_public, _try_openweather, _try_nws):
        result = src()
        if result is not None:
            return result
    return None


# ---------- helpers for the hourly historical log ----------

def fetch_pws_single(station_id: str) -> Optional[float]:
    url = "https://api.weather.com/v2/pws/observations/current"
    try:
        r = requests.get(
            url,
            params={"stationId": station_id, "format": "json", "units": "e", "apiKey": PUBLIC_WU_KEY},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        r.raise_for_status()
        obs = (r.json().get("observations") or [{}])[0]
        v = obs.get("imperial", {}).get("temp")
        return float(v) if v is not None else None
    except (requests.RequestException, ValueError, KeyError):
        return None


_CLUB_POOL_URL = "https://www.montesanoclub.org/pool"
_CLUB_POOL_TEMP_RE = re.compile(
    r"Pool temperature.{0,400}?(?P<temp>\d{1,3}\.\d{1,3})\s*(?:<!--[^>]*-->\s*)?°F",
    re.S,
)
_CLUB_POOL_AGE_RE = re.compile(
    r"Last updated\s*(?:<!--[^>]*-->\s*)?(?P<n>\d+)\s*(?P<unit>[smh])\s*ago"
)


def fetch_club_pool_temp() -> tuple[Optional[float], Optional[int]]:
    try:
        r = requests.get(_CLUB_POOL_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        body = r.text
    except requests.RequestException:
        return None, None

    m = _CLUB_POOL_TEMP_RE.search(body)
    if not m:
        return None, None
    temp_f = float(m.group("temp"))

    age_s: Optional[int] = None
    age_m = _CLUB_POOL_AGE_RE.search(body)
    if age_m:
        n = int(age_m.group("n"))
        unit = age_m.group("unit")
        age_s = n if unit == "s" else n * 60 if unit == "m" else n * 3600

    return temp_f, age_s


HOURLY_PWS_STATIONS = ("KALHUNTS560", "KALHUNTS264")


# ---------------------------------------------------------------- history

def fetch_pws_history_day(station_id: str, date_yyyymmdd: str) -> Optional[dict]:
    """Pull one day of 5-minute observations from WU history/all.

    `date_yyyymmdd` is the UTC-ish day key WU expects (e.g. "20260101").
    Returns the raw JSON, or None on failure. Caller is responsible for
    iterating obs and inserting via db.insert_pws_observation.
    """
    url = "https://api.weather.com/v2/pws/history/all"
    try:
        r = requests.get(
            url,
            params={
                "stationId": station_id,
                "format":    "json",
                "units":     "e",
                "date":      date_yyyymmdd,
                "apiKey":    PUBLIC_WU_KEY,
                "numericPrecision": "decimal",
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept":     "application/json",
                "Origin":     "https://www.wunderground.com",
                "Referer":    "https://www.wunderground.com/",
            },
            timeout=20,
        )
        if r.status_code == 204:
            return {"observations": []}
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[history] wu {station_id} {date_yyyymmdd} failed: {e}")
        return None


def fetch_nws_observations_range(station_id: str, since: datetime) -> list[dict]:
    """Pull the most-recent week-ish of observations from NWS for one station.

    NWS only keeps about a week of observations via this endpoint. For deeper
    history use synoptic/api.synopticdata.com (out of scope for now)."""
    url = f"https://api.weather.gov/stations/{station_id}/observations"
    headers = {
        "User-Agent": "pool-temp-monitor (kyleroden@gmail.com)",
        "Accept":     "application/geo+json",
    }
    params = {"start": since.astimezone(timezone.utc).isoformat(timespec="seconds")}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        feats = r.json().get("features") or []
        out = []
        for f in feats:
            props = f.get("properties") or {}
            ts = props.get("timestamp")
            if ts:
                out.append({"ts": ts, "props": props})
        return out
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"[history] nws {station_id} failed: {e}")
        return []


# ---------------------------------------------------------------- nws forecast

def fetch_nws_forecast() -> Optional[dict]:
    """Returns the NWS gridpoint forecast for KHSV's gridpoint as a dict with
    a `periods` list. Each period has `name`, `startTime`, `endTime`, `temperature`, etc."""
    points_url = f"https://api.weather.gov/points/{DEFAULT_LAT},{DEFAULT_LON}"
    headers = {
        "User-Agent": "pool-temp-monitor (kyleroden@gmail.com)",
        "Accept":     "application/geo+json",
    }
    try:
        r = requests.get(points_url, headers=headers, timeout=10)
        r.raise_for_status()
        forecast_url = r.json()["properties"]["forecast"]
        r2 = requests.get(forecast_url, headers=headers, timeout=10)
        r2.raise_for_status()
        return r2.json().get("properties")
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"[forecast] nws failed: {e}")
        return None

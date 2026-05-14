"""Outdoor temperature sources.

Resolves in priority order:
  1. Wunderground PWS (authenticated, if WUNDERGROUND_API_KEY env set)
  2. Wunderground PWS (public, uses the same anonymous key wunderground.com's
                       own dashboard widget uses; no signup required)
  3. OpenWeatherMap   (if OWM_API_KEY env set)
  4. NWS              (always available, no key; defaults to KHSV / Huntsville Intl)

Each call returns (temp_f, source_name, station_id_or_None, raw_response_dict).
"""

import os
import re
from typing import Optional

import requests

DEFAULT_LAT = 34.7304   # Huntsville AL approx
DEFAULT_LON = -86.5861
DEFAULT_NWS_STATION = "KHSV"  # Huntsville International Airport (HSV)

WU_KEY      = os.environ.get("WUNDERGROUND_API_KEY")
# Comma-separated station IDs, tried in order. Both stations are near
# Monte Sano in Huntsville AL; first one returning a valid temp wins.
WU_STATIONS = [s.strip() for s in os.environ.get(
    "WUNDERGROUND_STATION_IDS", "KALHUNTS560,KALHUNTS264"
).split(",") if s.strip()]
OWM_KEY     = os.environ.get("OWM_API_KEY")


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


PUBLIC_WU_KEY = "e1f10a1e78da46f5b10a1e78da96f525"


def _try_wunderground_public() -> Optional[tuple]:
    """Same v2 PWS endpoint, but with the anonymous key the wunderground.com
    dashboard widget uses. No account needed; works for any public PWS."""
    if not WU_STATIONS:
        return None
    url = "https://api.weather.com/v2/pws/observations/current"
    for station in WU_STATIONS:
        try:
            r = requests.get(
                url,
                params={
                    "stationId": station,
                    "format":    "json",
                    "units":     "e",
                    "apiKey":    PUBLIC_WU_KEY,
                },
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
    params = {
        "lat":   DEFAULT_LAT,
        "lon":   DEFAULT_LON,
        "units": "imperial",
        "appid": OWM_KEY,
    }
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
    """Fetch the current temp_f from one specific Wunderground PWS via the
    same anonymous key the dashboard widget uses. Returns None on any error."""
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
# Page is server-rendered Next.js. The temp ends up as literal markup like
#   Pool temperature</p><p class="...">72.0<!-- -->°F</p>
# with the actual U+00B0 char (not an escape). Find the first numeric value
# after "Pool temperature".
_CLUB_POOL_TEMP_RE = re.compile(
    r"Pool temperature.{0,400}?(?P<temp>\d{1,3}\.\d{1,3})\s*(?:<!--[^>]*-->\s*)?°F",
    re.S,
)
_CLUB_POOL_AGE_RE = re.compile(
    r"Last updated\s*(?:<!--[^>]*-->\s*)?(?P<n>\d+)\s*(?P<unit>[smh])\s*ago"
)


def fetch_club_pool_temp() -> tuple[Optional[float], Optional[int]]:
    """Scrape the water temp + 'last updated X ago' age (in seconds) from the
    public club site. Returns (temp_f, age_seconds) or (None, None) on failure."""
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


# Stations explicitly logged in the hourly historical record. Both are on
# Monte Sano in Huntsville. Keep order stable so column names stay meaningful.
HOURLY_PWS_STATIONS = ("KALHUNTS560", "KALHUNTS264")

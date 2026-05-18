"""Forecast assembly: KHSV -> Monte Sano air -> pool water.

This is intentionally not-yet-accurate. We're stacking three models, each of
which we can refine independently as more data arrives:

  1. NWS Huntsville (KHSV) forecast      [ground truth source]
              |
              v  + correction
  2. Monte Sano air forecast              ≈ KHSV + median(PWS - KHSV)
              |
              v  + thermal lag model
  3. Pool water forecast                  ≈ pool_now + k * (air_forecast - pool_now)

For (2): we use whatever paired history we have between the PWS stations and
KHSV. If we don't have any (the 'outdoor_readings' table only goes back as
far as the server's been running), we fall back to a static offset constant
the user can override with MS_AIR_OFFSET_F env.

For (3): same fallback — without enough water-air paired history we use a
hand-wave k=0.10/hour decay toward the air temp.

Everything is wrapped in 'method' and 'sample_size' fields so the UI can be
honest about how confident the prophecy actually is.
"""

from __future__ import annotations

import os
import statistics
from datetime import datetime, timedelta, timezone

import db
import weather


# Default ridge-vs-valley correction if we don't have enough paired data.
# Monte Sano is ~1700 ft above the valley floor. ~3-5°F cooler is typical
# (1°F per 270 ft ELR), occasionally up to 10°F on inversion days.
DEFAULT_MS_AIR_OFFSET_F = float(os.environ.get("MS_AIR_OFFSET_F", "-3.5"))

# Default pool-air coupling strength per forecast period (~6 h).
# k=0.06 means "pool drifts ~6% of the gap to air over the period". Real value
# depends on pool surface area, depth, wind, sun, pump-on-time. Refined by fit.
DEFAULT_POOL_K = float(os.environ.get("POOL_K", "0.06"))


def _paired_ms_offset() -> tuple[float | None, int]:
    """Returns (median offset of PWS - KHSV, number of paired hours).

    Uses hourly_log + outdoor_readings: for each hourly row that has
    air_550/air_264, find the nearest KHSV reading (within ±90 min) and
    take the difference. Median across the available pairs."""
    since = datetime.now(timezone.utc) - timedelta(days=60)
    hourly = db.hourly_log(since)
    if not hourly:
        return None, 0

    with db.connect() as c:
        khsv = c.execute(
            "SELECT ts, temp_f FROM outdoor_readings WHERE source='nws' AND ts >= ? ORDER BY ts ASC",
            (since.isoformat(timespec="seconds"),),
        ).fetchall()
        khsv_pts = [(datetime.fromisoformat(r["ts"]), r["temp_f"]) for r in khsv]

    if not khsv_pts:
        return None, 0

    deltas = []
    for row in hourly:
        try:
            t = datetime.fromisoformat(row["ts"])
        except (TypeError, ValueError):
            continue
        # nearest KHSV obs by walking; data is small so linear is fine.
        best = min(khsv_pts, key=lambda kv: abs((kv[0] - t).total_seconds()))
        if abs((best[0] - t).total_seconds()) > 90 * 60:
            continue
        ms_air_vals = [v for v in (row["air_550_f"], row["air_264_f"]) if v is not None]
        if not ms_air_vals:
            continue
        ms = sum(ms_air_vals) / len(ms_air_vals)
        deltas.append(ms - best[1])

    if not deltas:
        return None, 0
    return statistics.median(deltas), len(deltas)


def _fit_pool_k() -> tuple[float | None, int]:
    """Naïve fit of pool-air coupling using the hourly_log table.

    For each consecutive hourly pair (t, t+1h) where we have water_f at both
    timestamps and at least one valid ms air reading at t:
        observed_dt   = water_f[t+1] - water_f[t]
        forecasted_dt = k * (air_t - water_f[t])
        => k_t = observed_dt / (air_t - water_f[t])   (skipping degenerate cases)

    Median across all valid hourly pairs."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = db.hourly_log(since)
    rows = [r for r in rows if r["water_f"] is not None]
    if len(rows) < 2:
        return None, 0

    ks: list[float] = []
    for a, b in zip(rows, rows[1:]):
        ms_air_vals = [v for v in (a["air_550_f"], a["air_264_f"]) if v is not None]
        if not ms_air_vals:
            continue
        air = sum(ms_air_vals) / len(ms_air_vals)
        gap = air - a["water_f"]
        if abs(gap) < 1.0:                  # tiny gap => k is noise
            continue
        dt = b["water_f"] - a["water_f"]
        ks.append(dt / gap)

    if not ks:
        return None, 0
    # trim to inner-50% to drop pump-off / scrape-stale outliers
    ks.sort()
    n = len(ks)
    lo, hi = n // 4, n - n // 4
    inner = ks[lo:hi] or ks
    return statistics.median(inner), len(ks)


def assemble_prophecy() -> dict:
    """Returns a forecast bundle ready for the /forecast page.

    Shape:
        {
          "now": { "pool_f": float | None, "ms_air_f": float | None, "khsv_f": float | None },
          "ms_offset": { "value_f": float, "samples": int, "source": "fit" | "default" },
          "pool_k":    { "value":   float, "samples": int, "source": "fit" | "default" },
          "periods": [
            { "name": "Tonight", "start": "...", "end": "...",
              "khsv_f": 62, "ms_air_f": 58.5, "pool_f": 67.8,
              "short_forecast": "Mostly clear" }, ...
          ],
          "generated_at": iso,
        }
    """
    raw = weather.fetch_nws_forecast()
    periods_raw = (raw or {}).get("periods", []) if raw else []

    offset_val, offset_n = _paired_ms_offset()
    if offset_val is None:
        offset_val, offset_src = DEFAULT_MS_AIR_OFFSET_F, "default"
    else:
        offset_src = "fit"

    k_val, k_n = _fit_pool_k()
    if k_val is None or not -0.5 < k_val < 0.5:
        k_val, k_src = DEFAULT_POOL_K, "default"
    else:
        k_src = "fit"

    now_pool = db.latest_pool_reading()
    now_outdoor = db.latest_outdoor_reading()

    pool_now_f = now_pool["temp_f"] if now_pool else None
    pool_chain = pool_now_f
    out_periods = []
    for p in periods_raw[:8]:
        khsv_f = p.get("temperature")
        ms_air = (khsv_f + offset_val) if khsv_f is not None else None
        # Pool: keep applying k each period to the running chain.
        pool_f = None
        if pool_chain is not None and ms_air is not None:
            pool_chain = pool_chain + k_val * (ms_air - pool_chain)
            pool_f = pool_chain
        out_periods.append({
            "name":           p.get("name"),
            "start":          p.get("startTime"),
            "end":            p.get("endTime"),
            "is_daytime":     p.get("isDaytime"),
            "khsv_f":         khsv_f,
            "ms_air_f":       ms_air,
            "pool_f":         pool_f,
            "short_forecast": p.get("shortForecast"),
            "wind":           p.get("windSpeed"),
        })

    return {
        "now": {
            "pool_f":  pool_now_f,
            "khsv_f":  now_outdoor["temp_f"] if (now_outdoor and now_outdoor.get("source") == "nws") else None,
            "outdoor_source": now_outdoor.get("source") if now_outdoor else None,
            "outdoor_station": now_outdoor.get("station_id") if now_outdoor else None,
            "outdoor_f": now_outdoor["temp_f"] if now_outdoor else None,
        },
        "ms_offset": {"value_f": offset_val, "samples": offset_n, "source": offset_src},
        "pool_k":    {"value":   k_val,      "samples": k_n,      "source": k_src},
        "periods":   out_periods,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

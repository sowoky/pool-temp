# PWS station notes (KALHUNTS560 / KALHUNTS264)

Quick lookup for the two Weather Underground personal weather stations the
ingestion pipeline polls.

## Why we have two

PWS owners can take their stations offline, swap sensors, lose power, or
have their solar shield foul over with cobwebs. A second nearby station gives
us:

- Failover (the live cascade in `weather.fetch_outdoor` uses both)
- Calibration (any persistent gap between them is a real bias in one of them)
- Noise reduction by averaging when both are healthy

## How to backfill / refresh

```powershell
# 30 days of 5-minute observations for both stations
.\website\.venv\Scripts\python.exe tools\backfill-pws-history.py --days 30

# A year, resuming any already-stored days
.\website\.venv\Scripts\python.exe tools\backfill-pws-history.py --days 365 --resume

# Quick console summary of the delta after backfill
.\website\.venv\Scripts\python.exe tools\analyze-stations.py
```

`backfill-pws-history.py` uses the same anonymous WU dashboard key that
`weather.py` uses for live polling — no signup required. It pauses
`--sleep-ms` (default 400ms) between requests to be polite. WU does
rate-limit, but in practice this pace works for multi-month pulls in a
single run.

## How long the stations have existed

Most KAL* private WU stations go back 2–5 years. The backfill script will
stop early (after 14 empty days in a row) if it walks past the station's
deployment date. So `--days 2000` is fine — it'll auto-cap.

## Live cascade order

Look at `weather._try_wunderground_public()` — it tries `WU_STATIONS` in
order, returning the first valid response. Default order is
`KALHUNTS560,KALHUNTS264`. Override with:

```
WUNDERGROUND_STATION_IDS=KALHUNTS264,KALHUNTS560
```

if 560 turns out to be the worse station.

## When to switch back to a single source

Once the `/stations` page shows mean |Δ| > 1.0°F sustained, the cascade is
masking a real problem. Pick the station with the lower σ (it's better
shielded / less sun-biased) and remove the other from `WU_STATIONS`.

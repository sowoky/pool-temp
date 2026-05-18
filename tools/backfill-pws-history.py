#!/usr/bin/env python3
"""Backfill Weather Underground PWS history into the local data.db.

WU's `history/all` endpoint returns 5-minute observations for a single
station and a single UTC-ish day per request. We walk backwards from
"yesterday" for N days, for each configured station.

Usage:
    python tools/backfill-pws-history.py --days 30
    python tools/backfill-pws-history.py --days 730 --stations KALHUNTS560
    python tools/backfill-pws-history.py --days 365 --resume

`--resume` skips dates that already have observations in the DB.
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "website"))

import db        # noqa: E402
import weather   # noqa: E402


def already_have_day(station_id: str, ymd: str) -> int:
    """Returns the number of obs already stored for this station+day.
    `ymd` is YYYYMMDD; we convert to the YYYY-MM-DD prefix for SQL LIKE."""
    iso_day = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
    with db.connect() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM pws_history WHERE station_id = ? AND ts LIKE ?",
            (station_id, f"{iso_day}%"),
        ).fetchone()
    return row["n"] if row else 0


def backfill(stations: list[str], days: int, resume: bool, sleep_ms: int) -> None:
    db.init()
    today_utc = datetime.now(timezone.utc).date()
    inserted_total = 0

    for station in stations:
        print(f"\n=== {station} : backfilling {days} day(s) ===")
        empty_streak = 0
        for offset in range(1, days + 1):
            day = today_utc - timedelta(days=offset)
            ymd = day.strftime("%Y%m%d")

            if resume:
                have = already_have_day(station, ymd)
                if have > 0:
                    print(f"  {ymd}  skip  (already have {have} obs)")
                    continue

            raw = weather.fetch_pws_history_day(station, ymd)
            n = 0
            if raw is not None:
                obs_list = raw.get("observations") or []
                for obs in obs_list:
                    db.insert_pws_observation(station, obs)
                n = len(obs_list)
                inserted_total += n
            print(f"  {ymd}  {n} obs")

            empty_streak = empty_streak + 1 if n == 0 else 0
            if empty_streak >= 14:
                print(f"  ! 14 empty days in a row for {station} — stopping early "
                      f"(station likely didn't exist yet).")
                break

            time.sleep(sleep_ms / 1000.0)

    print(f"\nDone. Inserted {inserted_total:,} new observation rows total.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill PWS history.")
    ap.add_argument("--days", type=int, default=30,
                    help="how many days back from yesterday")
    ap.add_argument("--stations", type=str,
                    default="KALHUNTS560,KALHUNTS264",
                    help="comma-separated WU station IDs")
    ap.add_argument("--resume", action="store_true",
                    help="skip days that already have observations on file")
    ap.add_argument("--sleep-ms", type=int, default=400,
                    help="pause between requests; be polite to WU")
    args = ap.parse_args()

    stations = [s.strip() for s in args.stations.split(",") if s.strip()]
    backfill(stations, args.days, args.resume, args.sleep_ms)


if __name__ == "__main__":
    main()

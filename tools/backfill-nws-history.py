#!/usr/bin/env python3
"""Backfill NWS observations for KHSV into nws_history.

NWS only keeps ~7 days available via the public observations endpoint, so
this is mostly useful as a one-time pull plus a recurring catch-up. For
genuine multi-year history we'd need the Synoptic API (not wired up yet).
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "website"))

import db        # noqa: E402
import weather   # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--station", type=str, default="KHSV")
    args = ap.parse_args()

    db.init()
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    rows = weather.fetch_nws_observations_range(args.station, since)
    n = 0
    for r in rows:
        db.insert_nws_observation(args.station, r["ts"], r["props"])
        n += 1
    print(f"Inserted/refreshed {n} NWS observations for {args.station}.")


if __name__ == "__main__":
    main()

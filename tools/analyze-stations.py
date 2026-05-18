#!/usr/bin/env python3
"""Quick console summary of the PWS delta and which station looks more reliable.

Run after backfill-pws-history.py has populated pws_history.
"""

import sys
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "website"))

import db   # noqa: E402


def main() -> None:
    db.init()
    since = datetime.now(timezone.utc) - timedelta(days=730)
    paired = db.pws_paired_history("KALHUNTS560", "KALHUNTS264", since)
    paired = [r for r in paired if r["a_temp"] is not None and r["b_temp"] is not None]

    if not paired:
        print("No paired PWS observations on file. Run backfill-pws-history.py first.")
        return

    deltas = [r["a_temp"] - r["b_temp"] for r in paired]
    print(f"Paired observations on file: {len(paired):,}")
    print(f"  first:   {paired[0]['ts']}")
    print(f"  last:    {paired[-1]['ts']}")
    print(f"  mean:    {statistics.mean(deltas):+.3f} F  (KALHUNTS560 - KALHUNTS264)")
    print(f"  median:  {statistics.median(deltas):+.3f} F")
    print(f"  stdev:   {statistics.pstdev(deltas):.3f} F")
    print(f"  min/max: {min(deltas):+.2f} F / {max(deltas):+.2f} F")
    print(f"  mean abs delta: {sum(abs(d) for d in deltas) / len(deltas):.3f} F")

    # diurnal pattern: is one station hotter at noon?
    by_hour: dict[int, list[float]] = {}
    for r in paired:
        try:
            h = datetime.fromisoformat(r["ts"]).hour
        except (TypeError, ValueError):
            continue
        by_hour.setdefault(h, []).append(r["a_temp"] - r["b_temp"])

    print("\nMean delta by hour of day (UTC, KALHUNTS560 - KALHUNTS264):")
    for h in sorted(by_hour):
        n = len(by_hour[h])
        m = statistics.mean(by_hour[h])
        bar = "#" * min(40, int(abs(m) * 10))
        side = "+" if m >= 0 else "-"
        print(f"  {h:02d}h  n={n:5d}  {m:+.2f}F  {side}{bar}")


if __name__ == "__main__":
    main()

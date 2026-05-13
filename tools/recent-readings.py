"""Print recent pool readings with per-sensor breakdown."""

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).parent.parent / "website" / "data.db"
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 15

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

rows = con.execute(
    """
    SELECT pr.id, pr.ts, pr.temp_f AS primary_f, pr.remote_ip,
           GROUP_CONCAT(psr.addr || '=' || ROUND(psr.temp_f, 3), ' | ') AS sensors
      FROM pool_readings pr
      LEFT JOIN pool_sensor_readings psr ON psr.reading_id = pr.id
     GROUP BY pr.id
     ORDER BY pr.id DESC
     LIMIT ?
    """,
    (limit,),
).fetchall()

print(f"{'id':>5}  {'ts':<26}  {'primary':>8}  sensors")
print("-" * 110)
for r in rows:
    print(f"{r['id']:>5}  {r['ts']:<26}  {r['primary_f']:>6.2f}F   {r['sensors']}")

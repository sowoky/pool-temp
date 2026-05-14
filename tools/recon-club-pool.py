"""Look for what the club's /pool page actually exposes beyond the
displayed temperature value -- API endpoints, Next.js data blob, second
sensor reading, etc."""

import re
import sys
from pathlib import Path

import requests

URL = "https://www.montesanoclub.org/pool"
OUT = Path(r"C:\Users\kyler\workspace\pool-temp\tools\msc-pool-cache")
OUT.mkdir(parents=True, exist_ok=True)

r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
print(f"GET {URL} -> {r.status_code}  {len(r.text)} bytes")
(OUT / "pool.html").write_text(r.text, encoding="utf-8")
html = r.text

def search(label, pattern, flags=re.I, limit=20):
    matches = re.findall(pattern, html, flags)
    if not matches:
        return
    print(f"\n--- {label} ({len(matches)}) ---")
    seen = []
    for m in matches:
        s = m if isinstance(m, str) else m[0]
        if s in seen:
            continue
        seen.append(s)
        if len(seen) >= limit:
            break
        print(f"  {s[:200]}")

search("temp_f json", r'"temp_f"\s*:\s*[0-9.]+')
search("sensors array", r'"sensors"\s*:\s*\[[^\]]{0,500}\]')
search("temp keyword context", r'.{0,40}\btemp[A-Za-z_]{0,12}.{0,60}')
search("API paths", r'/api/[A-Za-z0-9_\-/.]+')
search("temps paths", r'/temps?/[A-Za-z0-9_\-/.]+')
search("Next.js data urls", r'/_next/data/[^"]{1,200}')
search("fetch() calls", r'fetch\([^)]{0,200}\)')
search("addresses (sensor ROM hex)", r'\b28[0-9A-F]{14}\b')

# Pull __NEXT_DATA__ blob explicitly.
m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
if m:
    blob = m.group(1)
    (OUT / "next-data.json").write_text(blob, encoding="utf-8")
    print(f"\n--- __NEXT_DATA__ blob: {len(blob)} bytes (saved next-data.json) ---")
    # show every key/value that looks temp-related
    for needle in ("temp_f", "sensors", "primary_addr", "label", "received_at", "raw_json", "addr"):
        for hit in re.finditer(rf'"{needle}"\s*:\s*("[^"]*"|\[[^\]]*\]|\{{[^}}]*\}}|[0-9.]+|true|false|null)', blob):
            print(f"   {needle}: {hit.group(0)[:300]}")
else:
    print("\n--- no __NEXT_DATA__ found; site may not be Next.js or uses RSC instead ---")

# Pull React Server Components flight payloads (newer Next).
flights = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)+)"\]\)', html)
if flights:
    full = "".join(flights)
    (OUT / "next-flight.txt").write_text(full, encoding="utf-8")
    print(f"\n--- next_f flight payloads: {len(flights)} chunks, {len(full)} bytes (saved next-flight.txt) ---")
    for needle in ("temp_f", "sensors", "addr", "label", "received_at", "primary_addr", "/api/", "/temps"):
        # decoded version with escapes resolved
        for hit in re.finditer(rf'{re.escape(needle)}[^,}}\]]{{0,200}}', full):
            print(f"   {hit.group(0)[:250]}")

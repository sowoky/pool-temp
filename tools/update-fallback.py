"""Set the ESP32's fallback endpoint URL via its admin page, then poll
the Flask server's /api/current to confirm fresh ingestion."""

import sys
import time

import requests

import os

ADMIN_URL    = "http://pool-temp.local/save"
ADMIN_AUTH   = ("admin", os.environ.get("ADMIN_PASS", "changeme"))
NEW_FALLBACK = sys.argv[1] if len(sys.argv) > 1 else "http://2.tcp.ngrok.io:17525/reading"
LOCAL_API    = "http://127.0.0.1:18080/api/current"


def main() -> int:
    print(f"--- POSTing fallback={NEW_FALLBACK!r} to admin ---")
    r = requests.post(
        ADMIN_URL,
        auth=ADMIN_AUTH,
        data={"endpoint_fallback": NEW_FALLBACK},
        timeout=10,
        allow_redirects=False,
    )
    print(f"status: {r.status_code}  location: {r.headers.get('Location')}")
    if r.status_code not in (200, 303):
        print(f"unexpected status; body: {r.text[:200]}")
        return 1

    print("\n--- waiting up to 90s for a fresh sample to land at the Flask server ---")
    start = time.time()
    last_id = None
    try:
        cur = requests.get(LOCAL_API, timeout=5).json()
        last_id = (cur.get("pool") or {}).get("ts")
        print(f"baseline pool.ts = {last_id}")
    except Exception as e:
        print(f"baseline fetch failed: {e}")

    while time.time() - start < 90:
        time.sleep(5)
        try:
            cur = requests.get(LOCAL_API, timeout=5).json()
            pool = cur.get("pool") or {}
            ts = pool.get("ts")
            if ts and ts != last_id:
                print(f"\n*** NEW sample landed at {ts}, pool {pool.get('temp_f')} F ***")
                return 0
            print(f"  no new sample yet (ts={ts}, age={pool.get('age_seconds')})")
        except Exception as e:
            print(f"  poll error: {e}")
    print("\nNo new sample in 90s. Check serial monitor.")
    return 2


if __name__ == "__main__":
    sys.exit(main())

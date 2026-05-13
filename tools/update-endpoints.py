"""Update both endpoints via the admin page, then watch what the next sample uses."""

import os
import sys
import time

import requests

ADMIN_URL  = "http://pool-temp.local/save"
ADMIN_AUTH = ("admin", os.environ.get("ADMIN_PASS", "changeme"))
LOCAL_API  = "http://127.0.0.1:18080/api/current"


def main() -> int:
    primary  = sys.argv[1] if len(sys.argv) > 1 else ""
    fallback = sys.argv[2] if len(sys.argv) > 2 else ""

    data = {}
    if primary:  data["endpoint_primary"]  = primary
    if fallback: data["endpoint_fallback"] = fallback

    print(f"--- POSTing {data} ---")
    r = requests.post(ADMIN_URL, auth=ADMIN_AUTH, data=data, timeout=10, allow_redirects=False)
    print(f"status: {r.status_code}  loc: {r.headers.get('Location')}")
    if r.status_code not in (200, 303):
        return 1

    print("\n--- waiting up to 90s for fresh sample ---")
    last_ts = (requests.get(LOCAL_API, timeout=5).json().get("pool") or {}).get("ts")
    print(f"baseline ts: {last_ts}")
    start = time.time()
    while time.time() - start < 90:
        time.sleep(5)
        pool = requests.get(LOCAL_API, timeout=5).json().get("pool") or {}
        if pool.get("ts") and pool["ts"] != last_ts:
            print(f"\n*** NEW sample {pool['ts']}  {pool.get('temp_f')}F (age={pool.get('age_seconds')}s) ***")
            return 0
        print(f"  ts={pool.get('ts')} age={pool.get('age_seconds')}")
    print("\nNo new sample in 90s.")
    return 2


if __name__ == "__main__":
    sys.exit(main())

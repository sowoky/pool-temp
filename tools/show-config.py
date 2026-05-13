"""Pull the current config from the ESP32 admin page and show what the
device thinks its settings are, plus live telemetry."""

import os
import re

import requests

ADMIN_URL = "http://pool-temp.local/"
ADMIN_AUTH = ("admin", os.environ.get("ADMIN_PASS", "changeme"))

FIELDS = [
    "endpoint_primary",
    "endpoint_fallback",
    "api_key",
    "device_label",
    "sample_seconds",
    "min_f",
    "max_f",
    "primary_addr",
    "admin_user",
    "admin_pass",
    "ota_password",
]


def main() -> int:
    r = requests.get(ADMIN_URL, auth=ADMIN_AUTH, timeout=10)
    if r.status_code != 200:
        print(f"admin GET failed: {r.status_code}")
        return 1
    html = r.text

    print("=" * 70)
    print("DEVICE CONFIG (as currently stored in NVS)")
    print("=" * 70)
    for name in FIELDS:
        m = re.search(
            rf'name="{re.escape(name)}"\s+value="([^"]*)"', html
        )
        val = m.group(1) if m else "<not found>"
        print(f"  {name:25s} = {val}")

    print()
    print("=" * 70)
    print("LIVE TELEMETRY  (GET /status)")
    print("=" * 70)
    s = requests.get("http://pool-temp.local/status", timeout=5).json()
    for k, v in s.items():
        print(f"  {k:25s} = {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

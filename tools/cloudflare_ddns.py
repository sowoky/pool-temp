"""Cloudflare Dynamic DNS updater.

Detects this machine's public IP and updates a Cloudflare DNS A record
to match. Idempotent; only PATCHes when the IP actually changes.

Env vars:
    CF_API_TOKEN   API token with Zone:DNS:Edit scope for the zone
    CF_ZONE_NAME   apex zone, e.g. kyleroden.com
    CF_RECORD_NAME full record, e.g. kyleroden.com or pool.kyleroden.com
                   (default: same as CF_ZONE_NAME)

Usage:
    python cloudflare_ddns.py            # one-shot, cron-friendly
    python cloudflare_ddns.py --watch    # loop, sleeping 5min between checks
"""

import os
import sys
import time

import requests

API = "https://api.cloudflare.com/client/v4"


def _h(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }


def public_ip() -> str:
    """Use Cloudflare's trace endpoint (no third party, no rate limits)."""
    r = requests.get("https://1.1.1.1/cdn-cgi/trace", timeout=10)
    r.raise_for_status()
    for line in r.text.splitlines():
        if line.startswith("ip="):
            return line[3:]
    raise RuntimeError("could not parse public IP from cloudflare trace")


def zone_id(token: str, name: str) -> str:
    r = requests.get(f"{API}/zones", headers=_h(token), params={"name": name}, timeout=10)
    r.raise_for_status()
    result = r.json().get("result") or []
    if not result:
        raise RuntimeError(f"zone {name!r} not found in this Cloudflare account")
    return result[0]["id"]


def find_record(token: str, zid: str, record_name: str) -> dict | None:
    r = requests.get(
        f"{API}/zones/{zid}/dns_records",
        headers=_h(token),
        params={"type": "A", "name": record_name},
        timeout=10,
    )
    r.raise_for_status()
    result = r.json().get("result") or []
    return result[0] if result else None


def upsert(token: str, zid: str, record_name: str, ip: str, proxied: bool = True) -> str:
    existing = find_record(token, zid, record_name)
    if existing and existing["content"] == ip and existing.get("proxied") == proxied:
        return "no-change"
    payload = {
        "type":    "A",
        "name":    record_name,
        "content": ip,
        "ttl":     1,           # auto, since proxied
        "proxied": proxied,
        "comment": "managed by cloudflare_ddns.py",
    }
    if existing:
        r = requests.put(
            f"{API}/zones/{zid}/dns_records/{existing['id']}",
            headers=_h(token), json=payload, timeout=10,
        )
        r.raise_for_status()
        return f"updated {existing['content']} -> {ip}"
    r = requests.post(f"{API}/zones/{zid}/dns_records", headers=_h(token), json=payload, timeout=10)
    r.raise_for_status()
    return f"created -> {ip}"


def tick() -> None:
    token       = os.environ["CF_API_TOKEN"]
    zone_name   = os.environ["CF_ZONE_NAME"]
    record_name = os.environ.get("CF_RECORD_NAME", zone_name)
    ip          = public_ip()
    zid         = zone_id(token, zone_name)
    msg         = upsert(token, zid, record_name, ip, proxied=True)
    print(f"[ddns] {record_name} ip={ip}  {msg}")


def main() -> int:
    watch = "--watch" in sys.argv
    while True:
        try:
            tick()
        except KeyError as e:
            print(f"[ddns] missing env var: {e}", file=sys.stderr)
            return 2
        except requests.HTTPError as e:
            body = e.response.text if e.response is not None else ""
            print(f"[ddns] HTTP error: {e}  body={body[:300]}", file=sys.stderr)
        except Exception as e:
            print(f"[ddns] error: {e}", file=sys.stderr)
        if not watch:
            return 0
        time.sleep(300)


if __name__ == "__main__":
    sys.exit(main())

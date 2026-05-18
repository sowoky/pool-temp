# Firmware releases

How firmware updates work end-to-end, since the previous Caddy-based
publishing host was decommissioned.

## TL;DR

```
You bump FW_VERSION in src/main.cpp, commit, push.
       ↓
GitHub Actions runs .github/workflows/firmware.yml
       ↓
Builds, commits firmware-<VERSION>.bin + latest.json back to main,
creates a Release v<VERSION> with the .bin attached.
       ↓
ESP32 polls latest.json every hour. Sees new version → downloads new .bin → reflashes.
```

That's it. The device gets the new firmware in ≤ 1 hour without you touching it.

## URLs everything is anchored to

- Manifest (what the device polls):
  `https://raw.githubusercontent.com/sowoky/pool-temp/main/website/static/firmware/latest.json`
- Binary (the manifest points the device at this):
  `https://raw.githubusercontent.com/sowoky/pool-temp/main/website/static/firmware/firmware-<VERSION>.bin`
- Release page (human-facing changelog + download UI):
  `https://github.com/sowoky/pool-temp/releases`

The device follows the URL string inside the manifest, so we can move the
binary to a different host any time by editing only the manifest.

## One-time setup: GitHub Secrets

`src/secrets.h` (WiFi credentials) is gitignored, so the CI runner has no
copy. Add these four secrets at
**Settings → Secrets and variables → Actions** before CI can build a
publishable firmware:

| Secret name        | Value                                               |
|--------------------|-----------------------------------------------------|
| `PT_DEV_SSID`      | Primary WiFi SSID the device tries first            |
| `PT_DEV_PASS`      | Its password                                        |
| `PT_FALLBACK_SSID` | Secondary WiFi SSID (e.g. pool's network)           |
| `PT_FALLBACK_PASS` | Secondary password — leave **unset** for an open network |

If `PT_DEV_SSID` isn't set the build fails fast (with a clear error) so we
never accidentally publish a binary with stub creds that would brick the
device on update.

## How to cut a release

1. Edit `src/main.cpp` → bump `FW_VERSION` (e.g. `"1.1.1"` → `"1.1.2"`).
2. Commit and push to `main`.
3. Watch the Actions tab — `firmware build` runs (~1 minute).
4. Verify the new commit by `github-actions[bot]` lands on main with
   `firmware-1.1.2.bin` + updated `latest.json`.
5. Optional: check the new GitHub Release was created.

If you forget step 1, nothing happens — CI detects an existing
`firmware-<VERSION>.bin` and exits. So pushing src changes without a
version bump just gets skipped.

## Pushing OTA from a Mac (immediate install, no waiting for the poll)

Useful when you're physically at the pool and want to skip the hourly poll.

```bash
mkdir -p /tmp/pt && cd /tmp/pt

# 1. Pull the binary from GitHub raw (substitute the version you want)
curl -fSL -o firmware.bin \
  https://raw.githubusercontent.com/sowoky/pool-temp/main/website/static/firmware/firmware-1.1.1.bin

# 2. Pull the official espota.py (no local server required)
curl -fSL -o espota.py \
  https://raw.githubusercontent.com/espressif/arduino-esp32/master/tools/espota.py

# 3. Push to the device (must be on the same wifi)
python3 espota.py -i pool-temp.local -p 3232 --auth=pool-ota -f firmware.bin -d
```

If mDNS doesn't resolve at the pool (some APs block multicast):
- Find the device IP in the router admin or via the device's serial log
- Replace `-i pool-temp.local` with `-i 192.168.x.x`

## Rollback

Two ways:

- **Soft:** edit `latest.json` to point `"url"` at an older `firmware-X.Y.Z.bin`
  and change `"version"` to that older version. Push. Device picks it up.
- **Hard:** OTA-push an older binary directly using the Mac one-liner above.

The on-device version check is a strict string equality (`strcmp`), not a
semver comparison. So 1.1.0 will happily replace 1.1.1 if the manifest
tells it to. That's the rollback escape hatch.

## What gets committed by CI

Each release commit by CI touches exactly two files:
- `website/static/firmware/firmware-<VERSION>.bin` (the new binary)
- `website/static/firmware/latest.json` (updated to point at it)

That's ~1 MB of repo growth per release. After 100 releases the repo will
have ~100 MB of firmware history — fine for the lifetime of this project.
Old `firmware-*.bin` files can be deleted from the repo at any time; the
manifest only references the current one.

## Why we don't pin to a release asset URL

GitHub release asset URLs do a `302` redirect to `objects.githubusercontent.com`,
which adds a moving piece (cert chain, redirect-handling, host availability)
to a firmware-update path that should be boring. `raw.githubusercontent.com`
serves the file directly with a `200`. Same content, fewer ways to fail.

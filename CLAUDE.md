# Pool Temperature Monitor (ESP32 firmware)

## Project goal

WiFi-connected pool thermometer for our neighborhood pool. An ESP32 reads
one or more DS18B20 probes strapped to the filter-return PVC line and
POSTs JSON readings to an external HTTP endpoint every ~60 seconds. The
endpoint is owned by someone else (the club's web admin) — **this repo is
firmware-only.**

> **Scope note (2026-05-14):** the `website/` and `test-server/`
> subdirectories are *orphaned* — they're the receiver we ran for early
> bring-up. They are no longer part of this project; treat them as
> read-only reference. The Caddy reverse-proxy that fronted that local
> server has been removed; the Windows service `PoolTempCaddy` is stopped
> and disabled (see `tools\disable-services.ps1` if you ever need to
> redo the cleanup on another box).

## Hardware

- **MCU:** ESP32 dev board (WROOM-32D variant, generic `esp32dev` in PlatformIO). CH9102 USB-serial bridge.
- **Sensor:** Waterproof DS18B20 probe (1-Wire, stainless sheath) salvaged from an old BrewPiLess fermenter rig — known good, used in food/liquid environments for years
- **Pull-up:** 4.7kΩ between data line and 3.3V (confirm whether the probe cable already includes one before adding)
- **Power:** USB (5V) from a nearby outlet at the pool equipment pad
- **Enclosure:** IP65 project box with cable gland

### Wiring

```
DS18B20 (3-wire waterproof):
  Red    → ESP32 3.3V   (NOT 5V — ESP32 GPIO is not 5V-tolerant)
  Black  → ESP32 GND
  Yellow → ESP32 GPIO 13 (data)
  4.7kΩ pull-up between Yellow and 3.3V  (often already in the probe pigtail)
```

GPIO 13 sits next to a GND pin on the standard 30-pin DevKit V1 layout, so a 2-pin dupont housing lands directly on data + ground.

### Mounting

Probe is strap-mounted to PVC on the return line *after* the filter (active flow = real pool temp, not stagnant pipe temp).

- Thermal paste between probe tip and pipe
- Foil/HVAC aluminum tape to hold probe tight against pipe
- Black foam pipe insulation sleeve over the whole assembly
- Expect ~1–2°F lag/offset vs. true water temp; fine for "what's the pool temp" display purposes
- Readings drift toward ambient when pump is off (water stagnates in the pipe)

## Software

### Toolchain

- **Editor:** any; PlatformIO drives the build
- **Build:** PlatformIO (`pio run -e esp32dev -t upload`, `-t monitor` for serial). Works on kyle-mac (the primary dev box) — flash/monitor over the USB serial port directly.
- **Framework:** Arduino on ESP32 (`platform = espressif32`)
- The `tools/*.ps1` helpers are Windows-only conveniences; the cross-platform path is `pio` + the `python tools/*.py` scripts.

### Firmware behavior (`src/main.cpp`)

- Enumerates up to 8 DS18B20 sensors on the bus
- Reads every 60s (configurable in NVS)
- Scans for one of two known WiFi networks at boot (dev SSID + pool SSID)
- Auto-reconnects on WiFi drop
- Bounds-checks reading (0–130°F) before POSTing; rejects `DEVICE_DISCONNECTED_F`
- POSTs JSON `{"sensors":[...], "temp_f":78.4, "fw":"1.1.3", "label":"pool-equip-shed"}` with the `X-API-Key` header to BOTH configured endpoints (`endpoint_1` and `endpoint_2`) every cycle, independently — there is no primary→fallback cascade; each delivery succeeds or fails on its own (`postReading()` in `src/main.cpp`). A blank endpoint is skipped. Payload includes `fw` (firmware version) and `label` (device label).
- HTTPS endpoints use `setInsecure()` — TLS still encrypts the bytes on the wire, `X-API-Key` is the real auth, and this lets the firmware POST to any HTTPS receiver regardless of CA without us having to manage a root store on a small box
- **Self-update (OTA over HTTPS):** `checkForUpdate()` polls a manifest URL hourly (`au_url`, default the GitHub raw `latest.json`); if its `version` differs from `FW_VERSION` it downloads the referenced binary and reflashes via `httpUpdate` (reboots on success). Controlled by NVS `au_enabled` / `au_url` / `au_period`. See `docs/firmware-releases.md`.
- ArduinoOTA over WiFi also available for manual pushes without unscrewing the enclosure
- mDNS `pool-temp.local` for on-device discovery (the device's own mDNS hostname; unrelated to the LAN `.lan` records)
- Tiny admin web server on port 80 of the device — basic-auth form for editing the endpoint URLs, API key, sample period, label, OTA password (see `src/admin_page.cpp`)

### Endpoint contract

Canonical: **`docs/server-endpoint-spec.md`**. Each reading is POSTed to BOTH `endpoint_1` and `endpoint_2` independently (`X-API-Key` auth, JSON body, any 2xx = delivered). The firmware's NVS defaults (`src/config.cpp`) are `endpoint_1 = https://www.montesanoclub.org/temps/update` and `endpoint_2 = https://temp.kyro-labs.com/reading`; running values live in NVS and are editable via `http://pool-temp.local/` (basic auth) or `tools/update-endpoints.py`.

## Tools

ESP32-side helpers (`tools/`):

- `flash.ps1`, `flash-auto.ps1` — esptool wrappers; see [the board-quirks memory] for the manual BOOT-dance timing this hardware needs
- `monitor.ps1` — serial monitor at 115200
- `chip-id.ps1` — read MAC + chip rev
- `show-config.py` — scrape current NVS config + `/status` telemetry from `http://pool-temp.local/`
- `update-endpoints.py` — push new `endpoint_1`/`endpoint_2` URLs to the device admin page, then poll for a fresh sample as confirmation
- `update-fallback.py` — same idea, `endpoint_2`-only
- `tcp-probe.py` — quick connectivity sanity check
- `disable-services.ps1` — one-time cleanup (run elevated) for the now-removed Caddy + DDNS bits on the Windows host

## Test plan

1. Wire sensor on breadboard, **not** in pool yet
2. Build & upload — serial should show `DS18B20 devices found: N` and `[wifi] connected ...`
3. Hand-warm vs. ice-water vs. tap-water sanity check — readings should track
4. Confirm both endpoints return 2xx (each is POSTed independently every cycle; one failing doesn't stop the other)
5. Build enclosure, mount on PVC, deploy

## Owner / context

- Personal project for the neighborhood pool. Owner background, technical fluency, and comms style live in the `kyle-context` skill + global `claude-config/CLAUDE.md` — not re-derived here.
- Project-local anecdote: the DS18B20 probe was salvaged from an old BrewPiLess fermenter rig (known good, used in food/liquid for years), so OneWire is familiar territory.

## Future / nice-to-have

- Watchdog timer for total hangs (not just WiFi drops)
- Hard-code which sensor's ROM address is "primary" so swapping cables doesn't change which reading is authoritative
- Pump-on detection via a current clamp on the pump leg, so the receiver can flag stale readings when the pump is off — overkill for v1

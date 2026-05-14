# Pool Temperature Monitor

WiFi-connected pool thermometer for a neighborhood pool. An ESP32 reads
one or more DS18B20 waterproof probes strapped to the filter-return line
and POSTs JSON readings every ~60 seconds to an external HTTP receiver.

> **Scope:** this repo is now **firmware-only**. The `website/` and
> `test-server/` subdirectories are orphaned reference code from earlier
> bring-up; they're no longer part of the project. The Caddy reverse
> proxy that fronted the local receiver has been removed. See
> `tools\disable-services.ps1` for the one-shot cleanup that stops and
> disables the `PoolTempCaddy` service on Windows.

## Hardware

- **MCU**: ESP32 dev board, WROOM-32D variant (PlatformIO `esp32dev`), CH9102 USB-serial
- **Sensor**: Waterproof DS18B20 probe (1-Wire, stainless sheath)
- **Pull-up**: 4.7 kΩ from data to 3.3 V (often baked into the probe pigtail — meter before adding)
- **Power**: USB at the pool equipment pad
- **Enclosure**: IP65 with a cable gland

### Wiring (3-wire waterproof probe)

```
Red    -> ESP32 3.3 V   (NOT 5 V -- ESP32 GPIO is not 5 V tolerant)
Black  -> ESP32 GND
Yellow -> ESP32 GPIO 13 (data)
4.7 kOhm pull-up between Yellow and 3.3 V (often already in the probe cable)
```

`GPIO 13` is chosen because it sits next to a GND pin on the standard 30-pin
DevKit V1 layout, so a 2-pin dupont housing can land directly on data + ground.

### Mounting

Strap the probe to PVC on the return line *after* the filter (active flow ==
real pool temp, not stagnant pipe temp).

1. Thermal paste between probe tip and pipe.
2. Foil / HVAC aluminum tape pressing the probe against the pipe.
3. Black foam pipe insulation sleeve over the whole assembly.
4. Expect a 1–2 °F lag versus true water temperature — fine for
   "is the pool warm yet?" purposes.

The reading drifts toward ambient when the pump is off (water in the pipe
stagnates).

## Software

```
                                    +-----------------------+
   DS18B20 ---OneWire--- ESP32 ---> | external HTTP receiver |
                                    |  POST <url>           |
                                    |  X-API-Key: <key>     |
                                    +-----------------------+
                                       ^
                            JSON every 60s; falls over
                            to a secondary URL on non-2xx
```

### Firmware: `src/main.cpp`

Reads up to 8 DS18B20 sensors on the bus, scans for one of two known WiFi
networks at boot (a home / dev SSID and the pool's public SSID), and POSTs
JSON to a configurable endpoint every minute. Bounds-checks every reading and
rejects `DEVICE_DISCONNECTED_F`. Reconnects WiFi on drops. Serial debug at
115200 baud.

POST payload shape:

```json
{
  "sensors": [
    {"addr": "28XXXXXXXXXXXXE5", "temp_f": 78.5},
    {"addr": "28YYYYYYYYYYYYE6", "temp_f": 78.6}
  ],
  "temp_f": 78.5
}
```

`temp_f` at the top level is the "primary" reading (whichever sensor
enumerated first, unless you pin a specific ROM address via `primary_addr`).
The `sensors` array preserves every individual reading with its 64-bit ROM
address.

**Authentication:** every POST sends an `X-API-Key` header. Default
`dev-key`, rotatable via the device admin page (basic auth) or
`tools\update-endpoints.py`.

**HTTPS:** when the configured URL is `https://`, the firmware validates
against the pinned Let's Encrypt ISRG Root X1 (in `src/main.cpp`) rather
than disabling cert checks. ALPN is set to `http/1.1` so CDNs / ngrok edges
that require it don't drop the handshake.

**Runtime config (NVS, see `src/config.cpp`):**

| Key | Default | Purpose |
|---|---|---|
| `endpoint_primary` | `http://montesanoclub.org/temps/update` | first URL tried |
| `endpoint_fallback` | `https://niece-tweet-flame.ngrok-free.dev/reading` | retried on non-2xx |
| `api_key` | `dev-key` | `X-API-Key` value |
| `sample_period_ms` | `60000` | how often we sample + POST |
| `min_valid_f` / `max_valid_f` | `0.0` / `130.0` | bounds-reject before sending |
| `primary_addr` | `""` | ROM address of the "authoritative" sensor (optional) |
| `device_label` | `pool-equip-shed` | tag included in payload |
| `admin_user` / `admin_pass` | `admin` / `changeme` | basic auth for the device's web UI |
| `ota_password` | `pool-ota` | ArduinoOTA auth |

Endpoint contract (what the receiver needs to accept) is in
`docs/server-endpoint-spec.md`.

### On-device admin web UI

Once the ESP32 is on WiFi, it advertises mDNS as `pool-temp.local` and
hosts a tiny HTTP admin server on port 80:

| Verb | Path | Purpose |
|---|---|---|
| GET  | `/`       | HTML form for editing the runtime config (basic auth) |
| POST | `/save`   | persist form values to NVS (basic auth) |
| GET  | `/status` | JSON telemetry (no auth) |
| POST | `/reboot` | reboot the device (basic auth) |

### ArduinoOTA

Hostname `pool-temp.local`, password from NVS (`ota_password`). Useful
once the box is sealed.

## Quick start

```bash
# from project root, with PlatformIO installed
cp src/secrets.example.h src/secrets.h     # fill in WiFi creds (DEV + FALLBACK)
pio run -e esp32dev -t upload -t monitor
```

You should see:

```
=== pool-temp boot ===
[cfg] primary=...
[cfg] fallback=...
[1wire] DS18B20 devices found: N
  [0] 28...E5
[wifi] scanning...
[wifi] connecting to <ssid>...
[wifi] connected, IP=192.168.x.x, RSSI=-XX
[mdns] http://pool-temp.local/
[ota] ready
[temp] 28...E5 = 78.42 F
[json] {"sensors":[...],"temp_f":78.42}
[http] <url> -> 200 ...
```

If `DS18B20 devices found: 0` — check the pull-up resistor, GND, and the
GPIO 13 wire. If two sensors enumerate but their readings disagree by
>1 °F under matching conditions, one isn't in thermal contact.

## Tools

`tools/` contains firmware-side helpers only:

| Script | Purpose |
|---|---|
| `flash.ps1`, `flash-auto.ps1` | esptool wrappers — see the board-quirks notes in CLAUDE.md / Claude memory for the manual BOOT-dance timing this hardware needs |
| `monitor.ps1` | open the serial monitor at 115200 |
| `chip-id.ps1` | read MAC + chip rev |
| `show-config.py` | scrape current NVS config + telemetry from the device admin page |
| `update-endpoints.py` | push new primary/fallback URLs to the device, then poll a local API for a fresh sample as confirmation |
| `update-fallback.py` | same idea, fallback-only |
| `tcp-probe.py` | TCP sanity check against a host/port |
| `disable-services.ps1` | one-time cleanup (elevated) — stops & disables `PoolTempCaddy`, removes the firewall rules for 80/443. Safe to run again; idempotent. |

## File layout

```
pool-temp/
  CLAUDE.md             -- project notes / context for AI assistants
  README.md             -- this file
  platformio.ini        -- esp32dev env + library deps
  docs/
    server-endpoint-spec.md  -- contract for whoever runs the HTTP receiver
  src/
    main.cpp                 -- ESP32 firmware
    config.cpp / config.h    -- NVS-backed runtime config
    admin_page.cpp / .h      -- on-device admin web UI
    secrets.example.h        -- WiFi credentials template (committed)
    secrets.h                -- real WiFi credentials (gitignored)
  tools/                -- ESP32-side helpers (see table above)
  website/              -- ORPHANED. Old local receiver/dashboard. Not part of the project anymore.
  test-server/          -- ORPHANED. Tiny stdlib HTTP receiver used during bring-up.
```

## Future / nice-to-have

- Watchdog timer for total hangs (not just WiFi drops).
- Replace the "first sensor wins" primary-temp logic with a hard-coded
  ROM address so swapping the cable doesn't change which reading is
  authoritative.
- Pump-on detection via a current-sensing clamp on the pump leg, so the
  receiver can flag stale readings when the pump is off.

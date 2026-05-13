# Pool Temperature Monitor

A WiFi-connected pool thermometer for a neighborhood pool. An ESP32 reads a
DS18B20 waterproof probe strapped to the filter return line and POSTs JSON
readings to a small Flask website every minute. The website displays the
current pool temperature alongside an outdoor air temperature from a nearby
Wunderground PWS, with a historical chart over 24 hours, 7 days, or 30 days.

## Hardware

- **MCU**: ESP32 dev board, WROOM-32 variant (PlatformIO `esp32dev`)
- **Sensor**: Waterproof DS18B20 probe (1-Wire, stainless sheath)
- **Pull-up**: 4.7 k&Omega; from data to 3.3 V (often baked into the probe pigtail
  &mdash; check with a meter before adding)
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
4. Expect a 1&ndash;2&deg;F lag versus true water temperature &mdash; fine for
   &ldquo;is the pool warm yet?&rdquo; purposes.

The reading drifts toward ambient when the pump is off (water in the pipe
stagnates).

## Software architecture

```
                                +-----------------------------+
   DS18B20 ---OneWire--- ESP32  | Flask web app (Windows host)|
                          |     |  POST /reading              |
                          |     |  GET  /, /temperature       |  <--- browsers
                  HTTP POST     |  GET  /api/current          |
                  JSON every    |  GET  /api/history          |
                  60 seconds -> |  background outdoor poller  |
                                +-----------------------------+
                                              |
                                          SQLite
                                       website/data.db
```

### Firmware: `src/main.cpp`

Reads up to 8 DS18B20 sensors on the bus, scans for one of two known WiFi
networks at boot (a home / dev SSID and the pool&rsquo;s public SSID), POSTs
JSON to a configurable endpoint every minute. Bounds-checks every reading and
rejects `DEVICE_DISCONNECTED_F`. Reconnects WiFi on drops. Serial debug at
115200 baud.

POST payload shape (the test server, the production server, and the test
fixture all agree on this):

```json
{
  "sensors": [
    {"addr": "28XXXXXXXXXXXXE5", "temp_f": 78.5},
    {"addr": "28YYYYYYYYYYYYE6", "temp_f": 78.6}
  ],
  "temp_f": 78.5
}
```

`temp_f` at the top level is the &ldquo;primary&rdquo; reading (whichever
sensor enumerated first &mdash; pin this in firmware if you care which is
authoritative). The `sensors` array preserves every individual reading with
its 64-bit ROM address.

Authentication: every POST sends an `X-API-Key` header. The default is
`dev-key`; set `POOL_API_KEY` in the website&rsquo;s environment to rotate.

### Website: `website/`

Flask + Waitress + SQLite + Jinja2 + Chart.js (client-side from CDN). No
build step.

| File | Purpose |
|------|---------|
| `app.py` | Routes, ingestion endpoint, background outdoor weather poller |
| `db.py` | SQLite schema + helpers (`pool_readings`, `pool_sensor_readings`, `outdoor_readings`) |
| `weather.py` | Outdoor temperature source chain (see below) |
| `templates/` | `base.html`, `index.html`, `temperature.html` (Jinja2) |
| `static/` | `style.css`, `app.js` (live-tile hydration), `temperature.js` (Chart.js) |
| `run.bat` | One-click venv-and-start for dev |

#### Outdoor temperature sources

Tried in order; the first one returning a valid reading wins:

1. **Wunderground PWS (authenticated)** &mdash; if `WUNDERGROUND_API_KEY` is
   set. Tries each station ID in `WUNDERGROUND_STATION_IDS`
   (comma-separated). Default order: `KALHUNTS560,KALHUNTS264` (both on
   Monte Sano in Huntsville, AL).
2. **Wunderground PWS (public)** &mdash; no key required. Uses the same
   anonymous key that `wunderground.com`&rsquo;s own dashboard widget uses.
   Subject to that key remaining accessible.
3. **OpenWeatherMap** &mdash; if `OWM_API_KEY` is set.
4. **NWS (api.weather.gov)** &mdash; always available, no key. Defaults to
   station `KHSV` (Huntsville International).

The background poller runs every 10 minutes (`WEATHER_POLL_SECONDS`).

#### HTTP API

| Verb | Path | Notes |
|------|------|-------|
| GET  | `/`             | Home page (live tiles + intro + features + CTA) |
| GET  | `/temperature`  | Historical chart page (range selector + stats grid) |
| GET  | `/api/current`  | JSON: latest pool + outdoor + age-in-seconds |
| GET  | `/api/history?range=24h\|7d\|30d` | JSON: pool + outdoor time series |
| POST | `/reading`      | Firmware ingestion. Requires `X-API-Key`. |
| GET  | `/healthz`      | `{"ok": true}` |

## Quick start

### 1. Build & flash the firmware

```bash
# from project root, with PlatformIO installed
cp src/secrets.example.h src/secrets.h     # fill in real WiFi creds
pio run -e esp32dev -t upload -t monitor
```

You should see:

```
=== pool-temp boot ===
[1wire] DS18B20 devices found: 2
  [0] 28...E5
  [1] 28...E6
[wifi] scanning...
[wifi] connecting to <ssid>...
.......
[wifi] connected, IP=192.168.x.x, RSSI=-XX
[temp] 28...E5 = 78.42 F
[json] {"sensors":[...],"temp_f":78.42}
[http] POST -> 200 {"ok": true, ...}
```

If `DS18B20 devices found: 0` &mdash; check the pull-up resistor, GND, and
the GPIO 13 wire. If 2 sensors enumerate but their readings disagree by
&gt;1&deg;F under matching conditions, one isn&rsquo;t in thermal contact.

### 2. Run the website locally

```bash
cd website
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py             # dev server on :18080
```

Open `http://localhost:18080/`. The ESP32 should be POSTing to whichever
machine matches the `ENDPOINT` constant in `src/main.cpp`; for development
that&rsquo;s the LAN IP of your desktop.

For production (a real WSGI server):

```bash
.venv\Scripts\waitress-serve --listen=0.0.0.0:18080 app:app
```

### 3. Install as a Windows service (autostart on boot)

```powershell
# Run as Administrator
.\tools\install-service.ps1
```

This installs NSSM (via winget if missing), stops any dev Flask process,
registers `PoolTempWebsite` as an autostart service running Waitress, and
puts logs in `website/logs/`.

Manage it with:

```powershell
Get-Service PoolTempWebsite
Restart-Service PoolTempWebsite
Stop-Service    PoolTempWebsite
```

### 4. Expose it on the public internet

Three approaches, in order of &ldquo;how fast can I demo this.&rdquo;

#### Option A: ngrok (fastest; great for demos)

```yaml
# %LOCALAPPDATA%\ngrok\ngrok.yml
version: "2"
authtoken: <your ngrok token>
tunnels:
  pool:
    proto: http
    addr: 18080
```

```powershell
ngrok start --all
# pull the public URL from http://127.0.0.1:4040/api/tunnels
```

Pros: no DNS, no port forwarding, no Windows networking quirks, immune to
VPN routing. Cons: random subdomain on free tier (claim a free static
domain in the dashboard to fix that).

#### Option B: Caddy + your own domain

Reverse-proxy on the Windows host, automatic Let&rsquo;s Encrypt certificates
via HTTP-01 challenge.

```powershell
# Run as Administrator
.\tools\install-caddy.ps1
```

The `Caddyfile` (`caddy/Caddyfile`) sets up the public hostname. Requires:

- DNS A record pointing at your public WAN IP
- Router/firewall forwarding 80 and 443 to the Windows host&rsquo;s LAN IP
- Nothing else on the host listening on 80/443

Two gotchas worth flagging:

- **WSL2 localhost forwarding**: any service inside WSL listening on `:80`
  silently reserves the Windows-side port. `wsl --shutdown` releases it, or
  set `localhostForwarding=false` in `%USERPROFILE%\.wslconfig`.
- **Hyper-V port reservations**: WinNAT can claim port ranges dynamically.
  If Caddy reports `Only one usage of each socket address...permitted` with
  nothing visibly bound, `netsh int ipv4 add excludedportrange protocol=tcp
  startport=80 numberofports=1` after stopping winnat.

#### Option C: Cloudflare Tunnel

Outbound from the Windows host to Cloudflare&rsquo;s edge. No port forwarding,
no DDNS, immune to VPN egress. Not scripted in this repo yet.

### 5. Dynamic DNS (only if you&rsquo;re using your own domain on a residential
   IP)

```powershell
# Run as Administrator
.\tools\install-ddns.ps1
```

Prompts for your Cloudflare API token (scope: Zone:DNS:Edit), zone name
(e.g. `example.com`), and record name. Stores them as machine-scope
environment variables and registers `PoolTempCloudflareDDNS` as a
scheduled task that runs every 5 minutes as SYSTEM. The script lives at
`tools/cloudflare_ddns.py`.

## File layout

```
pool-temp/
  CLAUDE.md                  -- project notes / context for AI assistants
  README.md                  -- this file
  platformio.ini             -- esp32dev env + library deps
  src/
    main.cpp                 -- ESP32 firmware
    secrets.example.h        -- WiFi credentials template (committed)
    secrets.h                -- real WiFi credentials (gitignored)
  website/
    app.py                   -- Flask app
    db.py                    -- SQLite layer
    weather.py               -- outdoor temp source chain
    requirements.txt
    run.bat
    templates/
      base.html, index.html, temperature.html
    static/
      style.css, app.js, temperature.js
  caddy/
    Caddyfile                -- reverse proxy + Let's Encrypt
  test-server/
    server.py                -- standalone stdlib HTTP receiver (legacy)
  tools/
    install-service.ps1      -- website as Windows service
    install-caddy.ps1        -- Caddy as Windows service + firewall
    install-ddns.ps1         -- Cloudflare DDNS scheduled task
    cloudflare_ddns.py       -- one-shot DDNS updater
```

## Environment variables

| Variable | Used by | Default |
|----------|---------|---------|
| `POOL_API_KEY` | website (`/reading` auth) | `dev-key` |
| `PORT` | website | `18080` |
| `WEATHER_POLL_SECONDS` | weather poller | `600` (10 min) |
| `WUNDERGROUND_API_KEY` | weather (authenticated PWS) | unset |
| `WUNDERGROUND_STATION_IDS` | weather (PWS list) | `KALHUNTS560,KALHUNTS264` |
| `OWM_API_KEY` | weather (OpenWeatherMap) | unset |
| `CF_API_TOKEN` | DDNS updater | required |
| `CF_ZONE_NAME` | DDNS updater | required |
| `CF_RECORD_NAME` | DDNS updater | defaults to zone name |

## Future / nice-to-have

- ArduinoOTA for over-the-air firmware updates &mdash; set up *before* the
  enclosure is sealed.
- A watchdog timer for total hangs (not just WiFi drops).
- Pump-on detection via a current-sensing clamp on the pump leg, so the
  website can flag stale readings when the pump is off.
- Replace the &ldquo;first sensor wins&rdquo; primary-temp logic with a
  hard-coded ROM address so swapping the cable doesn&rsquo;t change which
  reading is authoritative.

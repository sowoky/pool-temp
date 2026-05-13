# Pool Temperature Monitor

## Project goal

WiFi-connected pool thermometer for our neighborhood pool. ESP32 reads a DS18B20 probe strapped to the filter return PVC line, POSTs temperature readings to a web endpoint at ~1 minute intervals. The web admin will display the value on the pool's website.

## Hardware

- **MCU:** ESP32 dev board (WROOM-32 variant, generic "esp32dev" in PlatformIO)
- **Sensor:** Waterproof DS18B20 probe (1-Wire, stainless sheath) salvaged from an old BrewPiLess fermenter rig — known good, used in food/liquid environments for years
- **Pull-up:** 4.7kΩ between data line and 3.3V (confirm whether the probe cable already includes one before adding)
- **Power:** USB (5V) from a nearby outlet at the pool equipment pad
- **Enclosure:** IP65 project box with cable gland (to be sourced)

### Wiring

```
DS18B20 (3-wire waterproof):
  Red    → ESP32 3.3V   (NOT 5V — ESP32 GPIO is not 5V-tolerant)
  Black  → ESP32 GND
  Yellow → ESP32 GPIO 4 (data)
  4.7kΩ pull-up between Yellow and 3.3V
```

### Mounting

Probe is strap-mounted to PVC on the return line *after* the filter (active flow = real pool temp, not stagnant pipe temp).

- Thermal paste between probe tip and pipe
- Foil/HVAC aluminum tape to hold probe tight against pipe
- Black foam pipe insulation sleeve over the whole assembly
- Expect ~1–2°F lag/offset vs. true water temp; fine for "what's the pool temp" display purposes
- Readings will drift toward ambient when pump is off (water stagnates in the pipe)

## Software

### Toolchain

- **Editor:** VS Code on Windows (native, not WSL)
- **Build:** PlatformIO IDE extension
- **Framework:** Arduino on ESP32 (`platform = espressif32`)
- Project is on Windows filesystem — PlatformIO sees the COM port natively without WSL/usbipd

### platformio.ini

```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps =
    paulstoffregen/OneWire
    milesburton/DallasTemperature
```

### Firmware behavior

- Reads DS18B20 every 60 seconds
- WiFi auto-reconnect on drop
- Bounds-checks reading (0–130°F) before POSTing; rejects DEVICE_DISCONNECTED_F
- Serial debug output at 115200 baud so we can watch readings even before the endpoint is live
- POSTs JSON `{"temp_f": 78.42}` to the website endpoint with an `X-API-Key` header

### Endpoint (pending from web admin)

Need from admin:
- [ ] URL
- [ ] Auth method (assuming API key header, confirm)
- [ ] Required payload shape (just `temp_f`, or also timestamp / device ID / etc.)
- [ ] HTTP or HTTPS (if HTTPS, will use `WiFiClientSecure` with `setInsecure()` — low-stakes data, not worth managing certs)

## Current starting firmware

`src/main.cpp` — see file. Constants at top to fill in:
- `ssid`, `password` — pool WiFi creds
- `endpoint`, `apiKey` — from admin, currently empty (firmware skips POST and just prints to serial when endpoint is empty)

## Test plan

1. Wire sensor on breadboard, **not** in pool yet
2. Build & upload, confirm serial shows "DS18B20 devices found: 1"
3. Hand-warm vs. ice-water vs. tap-water sanity check — readings should track
4. Add WiFi creds, confirm connection in serial monitor
5. When endpoint arrives, fill in `endpoint` + `apiKey`, confirm POST returns 200
6. Then build enclosure, mount on PVC, deploy

## Owner / context

- Kyle Roden, working on this as a personal project for the neighborhood pool
- Uses ESP32/embedded comfortably — assume technical fluency; skip the basics
- Direct/technical communication preferred, no preamble or fluff
- BrewPiLess background means DS18B20 + OneWire is familiar territory

## Future / nice-to-have (post-MVP)

- ArduinoOTA for updates without unscrewing the enclosure — set up *before* sealing the box
- Watchdog timer for total hangs (not just WiFi drops)
- Maybe report pump-on detection if we ever wire a current sensor on the pump leg (would let the website flag stale readings during pump-off periods) — definitely overkill for v1

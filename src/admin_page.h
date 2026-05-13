// Tiny HTTP admin server on port 80. Exposes a form for editing the
// runtime config, plus a status JSON endpoint.
//   GET  /              -- HTML form (basic auth)
//   POST /save          -- save form values to NVS (basic auth)
//   GET  /status        -- JSON state (no auth)
//   POST /reboot        -- reboot the ESP32 (basic auth)
//
// Reachable at http://pool-temp.local/ once mDNS is up.
#pragma once
#include <Arduino.h>

void adminBegin();
void adminLoop();

struct AdminTelemetry {
  uint32_t boot_seconds;
  uint8_t  sensor_count;
  float    last_temp_f;
  uint32_t last_sample_ms;
  uint32_t posts_ok;
  uint32_t posts_failed;
  String   wifi_ssid;
  String   wifi_ip;
  int      wifi_rssi;
};
extern AdminTelemetry g_telemetry;

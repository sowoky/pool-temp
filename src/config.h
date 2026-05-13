// Runtime config persisted in NVS via Preferences.
// Editable via the admin web page on the ESP32 at http://pool-temp.local/.
#pragma once
#include <Arduino.h>

struct PoolConfig {
  String   endpoint_primary;    // e.g. http://montesanoclub.org/temps/update
  String   endpoint_fallback;   // e.g. https://...ngrok-free.dev/reading  (blank = skip)
  String   api_key;             // X-API-Key value sent on every POST

  uint32_t sample_period_ms;    // ms between samples (default 60000)
  float    min_valid_f;
  float    max_valid_f;
  String   primary_addr;        // ROM hex of authoritative sensor (blank => first found)

  String   admin_user;          // HTTP basic auth on the admin page
  String   admin_pass;
  String   ota_password;        // ArduinoOTA password (read once at boot)

  String   device_label;        // free-form label included in POST payload
};

extern PoolConfig g_config;

void loadConfig(PoolConfig& cfg);
void saveConfig(const PoolConfig& cfg);

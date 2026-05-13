// Runtime config persisted in NVS via Preferences.
// Editable via the admin web page on the ESP32 at http://pool-temp.local/.
#pragma once
#include <Arduino.h>

struct PoolConfig {
  // Two ingest endpoints. Each reading is POSTed to BOTH (independently --
  // failure of one no longer affects the other). Same X-API-Key for both.
  String   endpoint_1;          // e.g. https://www.montesanoclub.org/temps/update
  String   endpoint_2;          // e.g. https://temp.kyro-labs.com/reading  (blank = skip)
  String   api_key;             // X-API-Key value sent on every POST

  uint32_t sample_period_ms;    // ms between samples (default 60000)
  float    min_valid_f;
  float    max_valid_f;
  String   primary_addr;        // ROM hex of authoritative sensor (blank => first found)

  String   admin_user;          // HTTP basic auth on the admin page
  String   admin_pass;
  String   ota_password;        // ArduinoOTA password (read once at boot)

  String   device_label;        // free-form label included in POST payload

  // Self-update over HTTPS. Device polls the manifest URL on an interval;
  // if it advertises a different FW_VERSION, the device downloads the
  // referenced binary and reflashes itself.
  bool     auto_update_enabled;
  String   update_manifest_url; // e.g. https://temp.kyro-labs.com/static/firmware/latest.json
  uint32_t update_check_period_ms;
};

extern PoolConfig g_config;

void loadConfig(PoolConfig& cfg);
void saveConfig(const PoolConfig& cfg);

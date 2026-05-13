#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ESPmDNS.h>
#include <ArduinoOTA.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>

#include "secrets.h"      // DEV_SSID / DEV_PASS / FALLBACK_SSID / FALLBACK_PASS
#include "config.h"       // g_config / loadConfig / saveConfig
#include "admin_page.h"   // adminBegin / adminLoop / g_telemetry

// Hardware-fixed; not in NVS.
static const uint8_t  ONEWIRE_PIN     = 13;
static const uint8_t  SENSOR_RES_BIT  = 12;     // 0.0625 F resolution, ~750ms convert
static const char*    MDNS_HOSTNAME   = "pool-temp";

// ---------- globals ----------
OneWire oneWire(ONEWIRE_PIN);
DallasTemperature sensors(&oneWire);
uint8_t deviceCount = 0;
DeviceAddress addrs[8];

// ---------- helpers ----------
static String addrToHex(const DeviceAddress& a) {
  char buf[17];
  for (int i = 0; i < 8; i++) sprintf(&buf[i * 2], "%02X", a[i]);
  buf[16] = '\0';
  return String(buf);
}

static void connectWifi() {
  WiFi.mode(WIFI_STA);
  Serial.println("[wifi] scanning...");
  int n = WiFi.scanNetworks();
  bool devFound = false, fallbackFound = false;
  for (int i = 0; i < n; i++) {
    String s = WiFi.SSID(i);
    if (s == DEV_SSID)      devFound = true;
    if (s == FALLBACK_SSID) fallbackFound = true;
  }
  Serial.printf("[wifi] dev(%s)=%s  fallback(%s)=%s\n",
                DEV_SSID,      devFound      ? "yes" : "no",
                FALLBACK_SSID, fallbackFound ? "yes" : "no");

  const char* ssid = nullptr;
  const char* pass = nullptr;
  if (devFound) {
    ssid = DEV_SSID;      pass = DEV_PASS;
  } else if (fallbackFound) {
    ssid = FALLBACK_SSID; pass = FALLBACK_PASS;
  } else {
    Serial.println("[wifi] neither network in range, will retry next cycle");
    return;
  }

  WiFi.setHostname(MDNS_HOSTNAME);
  Serial.printf("[wifi] connecting to %s...\n", ssid);
  WiFi.begin(ssid, pass);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[wifi] connected to %s, IP=%s RSSI=%d\n",
                  WiFi.SSID().c_str(),
                  WiFi.localIP().toString().c_str(),
                  WiFi.RSSI());
    g_telemetry.wifi_ssid = WiFi.SSID();
    g_telemetry.wifi_ip   = WiFi.localIP().toString();
    g_telemetry.wifi_rssi = WiFi.RSSI();
  } else {
    Serial.println("[wifi] connect timeout");
  }
}

static void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.println("[wifi] disconnected, reconnecting");
  WiFi.disconnect();
  connectWifi();
}

static void discoverSensors() {
  sensors.begin();
  uint8_t n = sensors.getDeviceCount();
  Serial.printf("[1wire] DS18B20 devices found: %u\n", n);
  deviceCount = 0;
  for (uint8_t i = 0; i < n && i < 8; i++) {
    if (sensors.getAddress(addrs[deviceCount], i)) {
      sensors.setResolution(addrs[deviceCount], SENSOR_RES_BIT);
      Serial.printf("  [%u] %s\n", deviceCount, addrToHex(addrs[deviceCount]).c_str());
      deviceCount++;
    }
  }
  g_telemetry.sensor_count = deviceCount;
  if (deviceCount == 0) {
    Serial.println("[1wire] no sensors -- check wiring (pull-up? GPIO13? GND/3V3?)");
  }
}

// Try one endpoint. Returns true on 2xx.
static bool tryPost(const String& url, const String& payload) {
  if (url.length() == 0) return false;
  HTTPClient http;
  bool began;
  WiFiClientSecure secure;
  if (url.startsWith("https://")) {
    secure.setInsecure();
    began = http.begin(secure, url);
  } else {
    began = http.begin(url);
  }
  if (!began) {
    Serial.printf("[http] begin failed for %s\n", url.c_str());
    return false;
  }
  http.setConnectTimeout(5000);
  http.setTimeout(8000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", g_config.api_key);
  http.addHeader("ngrok-skip-browser-warning", "true");
  int code = http.POST(payload);
  String resp = http.getString();
  Serial.printf("[http] %s -> %d  %s\n", url.c_str(), code, resp.c_str());
  http.end();
  return code >= 200 && code < 300;
}

// Try primary then fallback (config-driven). First 2xx wins. Empty URLs skipped.
static void postReading(const String& payload) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[http] wifi down, skipping POST");
    g_telemetry.posts_failed++;
    return;
  }
  const String* urls[2] = { &g_config.endpoint_primary, &g_config.endpoint_fallback };
  for (int i = 0; i < 2; i++) {
    if (urls[i]->length() == 0) continue;
    if (tryPost(*urls[i], payload)) {
      if (i > 0) Serial.println("[http] succeeded on fallback");
      g_telemetry.posts_ok++;
      return;
    }
    if (i + 1 < 2 && urls[i + 1]->length() > 0) {
      Serial.println("[http] failover -> next endpoint");
    }
  }
  Serial.println("[http] all endpoints failed this cycle");
  g_telemetry.posts_failed++;
}

// ---------- arduino ----------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("=== pool-temp boot ===");

  loadConfig(g_config);
  Serial.printf("[cfg] primary=%s\n",  g_config.endpoint_primary.c_str());
  Serial.printf("[cfg] fallback=%s\n", g_config.endpoint_fallback.c_str());
  Serial.printf("[cfg] sample_ms=%lu  bounds=[%.1f, %.1f]  label=%s\n",
                (unsigned long)g_config.sample_period_ms,
                g_config.min_valid_f, g_config.max_valid_f,
                g_config.device_label.c_str());

  discoverSensors();
  connectWifi();

  if (WiFi.status() == WL_CONNECTED) {
    if (MDNS.begin(MDNS_HOSTNAME)) {
      MDNS.addService("http", "tcp", 80);
      Serial.printf("[mdns] http://%s.local/\n", MDNS_HOSTNAME);
    } else {
      Serial.println("[mdns] start failed");
    }

    ArduinoOTA.setHostname(MDNS_HOSTNAME);
    ArduinoOTA.setPassword(g_config.ota_password.c_str());
    ArduinoOTA.onStart([]() {
      Serial.println("[ota] update starting");
    });
    ArduinoOTA.onEnd([]() {
      Serial.println("\n[ota] update done");
    });
    ArduinoOTA.onProgress([](unsigned int p, unsigned int t) {
      Serial.printf("[ota] %u%%\r", (p * 100) / t);
    });
    ArduinoOTA.onError([](ota_error_t e) {
      Serial.printf("[ota] error %u\n", e);
    });
    ArduinoOTA.begin();
    Serial.println("[ota] ready");

    adminBegin();
  }
}

void loop() {
  // ArduinoOTA + admin server must be serviced every loop, not just when sampling.
  ArduinoOTA.handle();
  adminLoop();
  g_telemetry.boot_seconds = millis() / 1000;

  static uint32_t lastSample = 0;
  uint32_t now = millis();
  if (now - lastSample < g_config.sample_period_ms && lastSample != 0) {
    delay(20);
    return;
  }
  lastSample = now;

  ensureWifi();

  // Refresh wifi telemetry every cycle (RSSI in particular drifts).
  if (WiFi.status() == WL_CONNECTED) {
    g_telemetry.wifi_ssid = WiFi.SSID();
    g_telemetry.wifi_ip   = WiFi.localIP().toString();
    g_telemetry.wifi_rssi = WiFi.RSSI();
  }

  if (deviceCount == 0) {
    discoverSensors();
    if (deviceCount == 0) return;
  }

  sensors.requestTemperatures();

  StaticJsonDocument<512> doc;
  JsonArray arr = doc.createNestedArray("sensors");
  float primary = NAN;          // first valid reading
  float primaryByAddr = NAN;    // reading from the configured primary_addr (if any)

  for (uint8_t i = 0; i < deviceCount; i++) {
    float f = sensors.getTempF(addrs[i]);
    bool valid = (f != DEVICE_DISCONNECTED_F)
              && (f >= g_config.min_valid_f)
              && (f <= g_config.max_valid_f);
    String hex = addrToHex(addrs[i]);
    Serial.printf("[temp] %s = %.2f F %s\n", hex.c_str(), f, valid ? "" : "(rejected)");
    if (!valid) continue;
    JsonObject s = arr.createNestedObject();
    s["addr"]   = hex;
    s["temp_f"] = f;
    if (isnan(primary)) primary = f;
    if (g_config.primary_addr.length() > 0 && hex == g_config.primary_addr) {
      primaryByAddr = f;
    }
  }

  if (arr.size() == 0) {
    Serial.println("[temp] no valid readings this cycle");
    return;
  }

  float topLevel = !isnan(primaryByAddr) ? primaryByAddr : primary;
  doc["temp_f"] = topLevel;
  if (g_config.device_label.length() > 0) {
    doc["label"] = g_config.device_label;
  }

  g_telemetry.last_temp_f    = topLevel;
  g_telemetry.last_sample_ms = millis();

  String payload;
  serializeJson(doc, payload);
  Serial.printf("[json] %s\n", payload.c_str());
  postReading(payload);
}

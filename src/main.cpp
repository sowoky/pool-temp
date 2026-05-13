#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <ESPmDNS.h>
#include <ArduinoOTA.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>

#include "secrets.h"      // DEV_SSID / DEV_PASS / FALLBACK_SSID / FALLBACK_PASS
#include "config.h"       // g_config / loadConfig / saveConfig
#include "admin_page.h"   // adminBegin / adminLoop / g_telemetry

// Bumped per release. Self-update only fires when the manifest advertises
// a string different from this one.
static const char* FW_VERSION = "1.1.0";

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

// ngrok and many CDNs want ALPN=http/1.1.
static const char* k_alpn_protos[] = {"http/1.1", nullptr};

// Persistent across requests so we don't churn heap each cycle.
static WiFiClientSecure g_secureClient;
static bool g_secureClientReady = false;

static void ensureSecureClient() {
  if (g_secureClientReady) return;
  // Skip chain validation -- bytes are still TLS-encrypted, X-API-Key is
  // the real auth, and this lets us POST to any HTTPS endpoint regardless
  // of which CA issued its cert.
  g_secureClient.setInsecure();
  g_secureClient.setHandshakeTimeout(30);
  g_secureClient.setAlpnProtocols(k_alpn_protos);
  g_secureClientReady = true;
}

// Try one endpoint. Returns true on 2xx.
static bool tryPost(const String& url, const String& payload) {
  if (url.length() == 0) return false;

  HTTPClient http;
  WiFiClient plain;
  bool began;

  if (url.startsWith("https://")) {
    ensureSecureClient();
    g_secureClient.stop();
    began = http.begin(g_secureClient, url);
  } else {
    began = http.begin(plain, url);
  }

  if (!began) {
    Serial.printf("[http] begin failed for %s\n", url.c_str());
    return false;
  }
  http.setConnectTimeout(10000);
  http.setTimeout(15000);
  http.setFollowRedirects(HTTPC_FORCE_FOLLOW_REDIRECTS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", g_config.api_key);
  http.addHeader("ngrok-skip-browser-warning", "true");

  int code = http.POST(payload);
  String resp = http.getString();
  Serial.printf("[http] %s -> %d  %s\n", url.c_str(), code, resp.c_str());
  http.end();
  return code >= 200 && code < 300;
}

// POST every cycle to both configured endpoints, independently. Each gets
// its own counter; failure of one does not stop the other.
static void postReading(const String& payload) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[http] wifi down, skipping POSTs");
    g_telemetry.posts_ep1_failed++;
    g_telemetry.posts_ep2_failed++;
    return;
  }

  if (g_config.endpoint_1.length() > 0) {
    if (tryPost(g_config.endpoint_1, payload)) g_telemetry.posts_ep1_ok++;
    else                                       g_telemetry.posts_ep1_failed++;
  }
  if (g_config.endpoint_2.length() > 0) {
    if (tryPost(g_config.endpoint_2, payload)) g_telemetry.posts_ep2_ok++;
    else                                       g_telemetry.posts_ep2_failed++;
  }
}

// Periodic self-update over HTTPS. Fetches the manifest, compares its
// "version" field to FW_VERSION; if different, downloads the binary URL
// it advertises and applies it via the Update library (reboots on success).
static void checkForUpdate() {
  if (!g_config.auto_update_enabled) return;
  if (WiFi.status() != WL_CONNECTED)  return;
  if (g_config.update_manifest_url.length() == 0) return;

  g_telemetry.last_update_check_ms = millis();

  ensureSecureClient();
  g_secureClient.stop();

  HTTPClient http;
  WiFiClient plain;
  bool began;
  if (g_config.update_manifest_url.startsWith("https://")) {
    began = http.begin(g_secureClient, g_config.update_manifest_url);
  } else {
    began = http.begin(plain, g_config.update_manifest_url);
  }
  if (!began) {
    g_telemetry.last_update_result = "begin failed";
    Serial.println("[update] begin failed");
    return;
  }
  http.setConnectTimeout(10000);
  http.setTimeout(15000);
  int code = http.GET();
  if (code != 200) {
    String result = "manifest HTTP " + String(code);
    g_telemetry.last_update_result = result;
    Serial.printf("[update] %s\n", result.c_str());
    http.end();
    return;
  }
  String body = http.getString();
  http.end();

  StaticJsonDocument<512> doc;
  if (deserializeJson(doc, body)) {
    g_telemetry.last_update_result = "manifest parse error";
    Serial.println("[update] manifest parse error");
    return;
  }

  const char* manifest_version = doc["version"]   | "";
  const char* binary_url       = doc["url"]       | "";
  if (manifest_version[0] == 0 || binary_url[0] == 0) {
    g_telemetry.last_update_result = "manifest missing fields";
    Serial.println("[update] manifest missing version or url");
    return;
  }

  Serial.printf("[update] manifest version=%s url=%s\n", manifest_version, binary_url);
  if (strcmp(manifest_version, FW_VERSION) == 0) {
    g_telemetry.last_update_result = String("up to date (") + FW_VERSION + ")";
    return;
  }

  Serial.printf("[update] applying %s -> %s\n", FW_VERSION, manifest_version);
  g_telemetry.last_update_result = String("downloading ") + manifest_version;

  // HTTPUpdate handles streaming the binary into the Update flash region,
  // verifying it, switching the OTA partition, and rebooting on success.
  ensureSecureClient();
  g_secureClient.stop();
  httpUpdate.rebootOnUpdate(true);
  t_httpUpdate_return ret;
  if (String(binary_url).startsWith("https://")) {
    ret = httpUpdate.update(g_secureClient, binary_url);
  } else {
    WiFiClient plain2;
    ret = httpUpdate.update(plain2, binary_url);
  }

  switch (ret) {
    case HTTP_UPDATE_FAILED:
      g_telemetry.last_update_result = String("FAILED: ") + httpUpdate.getLastErrorString();
      Serial.printf("[update] FAILED: %s\n", httpUpdate.getLastErrorString().c_str());
      break;
    case HTTP_UPDATE_NO_UPDATES:
      g_telemetry.last_update_result = "no update";
      Serial.println("[update] no update");
      break;
    case HTTP_UPDATE_OK:
      // Shouldn't reach here -- rebootOnUpdate fires before this.
      g_telemetry.last_update_result = "OK (rebooting)";
      Serial.println("[update] OK, rebooting");
      break;
  }
}

// ---------- arduino ----------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.printf("=== pool-temp boot (fw %s) ===\n", FW_VERSION);

  loadConfig(g_config);
  Serial.printf("[cfg] endpoint_1=%s\n", g_config.endpoint_1.c_str());
  Serial.printf("[cfg] endpoint_2=%s\n", g_config.endpoint_2.c_str());
  Serial.printf("[cfg] sample_ms=%lu  bounds=[%.1f, %.1f]  label=%s\n",
                (unsigned long)g_config.sample_period_ms,
                g_config.min_valid_f, g_config.max_valid_f,
                g_config.device_label.c_str());
  Serial.printf("[cfg] auto_update=%s  url=%s  period=%lu min\n",
                g_config.auto_update_enabled ? "on" : "off",
                g_config.update_manifest_url.c_str(),
                (unsigned long)(g_config.update_check_period_ms / 60000));

  g_telemetry.fw_version = FW_VERSION;

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
    ArduinoOTA.onStart  ([]() { Serial.println("[ota] update starting"); });
    ArduinoOTA.onEnd    ([]() { Serial.println("\n[ota] update done"); });
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
  ArduinoOTA.handle();
  adminLoop();
  g_telemetry.boot_seconds = millis() / 1000;

  // Auto-update tick. Fire 30 seconds after boot (settling) and then on
  // the configured interval. Cheap when nothing's new.
  static uint32_t lastUpdateCheck = 0;
  uint32_t now = millis();
  if (g_config.auto_update_enabled &&
      WiFi.status() == WL_CONNECTED &&
      ((lastUpdateCheck == 0 && now > 30000) ||
       (lastUpdateCheck != 0 && now - lastUpdateCheck >= g_config.update_check_period_ms))) {
    lastUpdateCheck = now;
    checkForUpdate();
  }

  // Sample tick.
  static uint32_t lastSample = 0;
  if (now - lastSample < g_config.sample_period_ms && lastSample != 0) {
    delay(20);
    return;
  }
  lastSample = now;

  ensureWifi();

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
  float primary = NAN;
  float primaryByAddr = NAN;

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
  doc["temp_f"]  = topLevel;
  doc["fw"]      = FW_VERSION;
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

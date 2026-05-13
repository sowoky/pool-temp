#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>

#include "secrets.h"   // DEV_SSID / DEV_PASS / FALLBACK_SSID / FALLBACK_PASS
                       // -- copy secrets.example.h to secrets.h and fill in.

// Endpoints tried in order. First 2xx response wins. NULL-terminated.
// 1. Real club website -- not live yet, will 4xx/5xx for now and we fall through.
// 2. Static ngrok URL backed by the Flask app on the home desktop. Stable
//    forever; works regardless of LAN IP changes.
static const char* ENDPOINTS[] = {
  "http://montesanoclub.org/temps/update",
  "https://niece-tweet-flame.ngrok-free.dev/reading",
  nullptr,
};
static const char* API_KEY  = "dev-key";

static const uint8_t ONEWIRE_PIN     = 13;
static const uint32_t SAMPLE_PERIOD  = 60UL * 1000UL;   // 60s
static const float    MIN_VALID_F    = 0.0f;
static const float    MAX_VALID_F    = 130.0f;
static const uint8_t  SENSOR_RES_BIT = 12;              // 12-bit = 0.0625°F resolution, ~750ms convert

// ---------- globals ----------
OneWire oneWire(ONEWIRE_PIN);
DallasTemperature sensors(&oneWire);
uint8_t deviceCount = 0;
DeviceAddress addrs[8];   // support up to 8 probes on the bus

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
  if (deviceCount == 0) {
    Serial.println("[1wire] no sensors — check wiring (pull-up? GPIO13? GND/3V3?)");
  }
}

// Try one endpoint. Returns true on 2xx.
static bool tryPost(const char* url, const String& payload) {
  HTTPClient http;
  bool began;
  WiFiClientSecure secure;
  if (strncmp(url, "https://", 8) == 0) {
    // Skip cert validation -- low-stakes data, ngrok/origin will have a
    // real cert anyway. Avoids shipping a CA bundle in firmware.
    secure.setInsecure();
    began = http.begin(secure, url);
  } else {
    began = http.begin(url);
  }
  if (!began) {
    Serial.printf("[http] begin failed for %s\n", url);
    return false;
  }
  http.setConnectTimeout(5000);   // 5s to establish TCP/TLS
  http.setTimeout(8000);          // 8s for the response
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.addHeader("ngrok-skip-browser-warning", "true");
  int code = http.POST(payload);
  String resp = http.getString();
  Serial.printf("[http] %s -> %d  %s\n", url, code, resp.c_str());
  http.end();
  return code >= 200 && code < 300;
}

// Try every endpoint in order; first 2xx wins. Logs failover transitions.
static void postReading(const String& payload) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[http] wifi down, skipping POST");
    return;
  }
  for (size_t i = 0; ENDPOINTS[i] != nullptr; i++) {
    if (tryPost(ENDPOINTS[i], payload)) {
      if (i > 0) Serial.printf("[http] succeeded on fallback endpoint #%u\n", (unsigned)i);
      return;
    }
    if (ENDPOINTS[i + 1] != nullptr) {
      Serial.printf("[http] failover -> next endpoint\n");
    }
  }
  Serial.println("[http] all endpoints failed this cycle");
}

// ---------- arduino ----------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("=== pool-temp boot ===");
  discoverSensors();
  connectWifi();
}

void loop() {
  static uint32_t lastSample = 0;
  uint32_t now = millis();
  if (now - lastSample < SAMPLE_PERIOD && lastSample != 0) {
    delay(100);
    return;
  }
  lastSample = now;

  ensureWifi();

  if (deviceCount == 0) {
    // re-scan in case probe was plugged in after boot
    discoverSensors();
    if (deviceCount == 0) return;
  }

  sensors.requestTemperatures();

  StaticJsonDocument<512> doc;
  JsonArray arr = doc.createNestedArray("sensors");
  float primary = NAN;

  for (uint8_t i = 0; i < deviceCount; i++) {
    float f = sensors.getTempF(addrs[i]);
    bool valid = (f != DEVICE_DISCONNECTED_F) && (f >= MIN_VALID_F) && (f <= MAX_VALID_F);
    Serial.printf("[temp] %s = %.2f F %s\n",
                  addrToHex(addrs[i]).c_str(), f, valid ? "" : "(rejected)");
    if (!valid) continue;
    JsonObject s = arr.createNestedObject();
    s["addr"]   = addrToHex(addrs[i]);
    s["temp_f"] = f;
    if (isnan(primary)) primary = f;
  }

  if (arr.size() == 0) {
    Serial.println("[temp] no valid readings this cycle");
    return;
  }

  // Keep top-level temp_f for backward compat with the CLAUDE.md shape.
  doc["temp_f"] = primary;

  String payload;
  serializeJson(doc, payload);
  Serial.printf("[json] %s\n", payload.c_str());
  postReading(payload);
}

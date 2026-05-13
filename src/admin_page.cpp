#include "admin_page.h"
#include "config.h"
#include <WebServer.h>
#include <WiFi.h>

static WebServer server(80);
AdminTelemetry g_telemetry = {};

// ---------- helpers ----------
static bool requireAuth() {
  if (!server.authenticate(g_config.admin_user.c_str(), g_config.admin_pass.c_str())) {
    server.requestAuthentication();
    return false;
  }
  return true;
}

static String esc(const String& s) {
  String out;
  out.reserve(s.length() + 16);
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    switch (c) {
      case '&':  out += "&amp;";  break;
      case '<':  out += "&lt;";   break;
      case '>':  out += "&gt;";   break;
      case '"':  out += "&quot;"; break;
      case '\'': out += "&#39;";  break;
      default:   out += c;
    }
  }
  return out;
}

static String formHtml(bool saved) {
  String html;
  html.reserve(10240);
  html += R"HTML(<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>pool-temp admin</title>
<style>
:root { --teal:#006577; --orange:#e78024; --cream:#f4f1ed; --dark:#1a2e35; --border:#d7e3e4; }
* { box-sizing: border-box; }
body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 0; background: var(--cream); color: var(--dark); }
header { background: var(--teal); color: #fff; padding: 1.2rem 1.5rem; }
header h1 { margin: 0; font-size: 1.2rem; letter-spacing: .04em; }
header p  { margin: .35rem 0 0; opacity: .8; font-size: .85rem; }
main { max-width: 720px; margin: 1.5rem auto; padding: 0 1rem; }
section { background: #fff; border: 1px solid var(--border); border-radius: 10px; margin-bottom: 1.2rem; padding: 1.2rem 1.4rem; }
section h2 { margin: 0 0 1rem; font-size: 1rem; color: var(--teal); text-transform: uppercase; letter-spacing: .12em; }
.row { display: grid; grid-template-columns: 14rem 1fr; gap: 1rem; padding: .55rem 0; border-bottom: 1px dashed var(--border); align-items: center; }
.row:last-child { border-bottom: none; }
.row label { font-size: .85rem; font-weight: 600; }
.row .hint { display: block; font-weight: 400; color: #6b7e83; font-size: .75rem; margin-top: .15rem; }
.row input { width: 100%; padding: .5rem .65rem; border: 1px solid var(--border); border-radius: 6px; font-size: .95rem; font-family: inherit; }
.row input:focus { outline: 2px solid var(--teal); border-color: var(--teal); }
.actions { display: flex; gap: .75rem; margin-top: 1rem; }
button { background: var(--teal); color: #fff; border: none; padding: .7rem 1.4rem; border-radius: 999px; font-size: .85rem; font-weight: 600; cursor: pointer; letter-spacing: .04em; }
button.alt { background: #fff; color: var(--dark); border: 1px solid var(--border); }
button:hover { filter: brightness(1.05); }
.saved { background: #d4f0d8; color: #1a5f2c; padding: .6rem .9rem; border-radius: 6px; margin-bottom: 1rem; font-size: .9rem; }
.status table { width: 100%; border-collapse: collapse; font-size: .9rem; }
.status td { padding: .25rem .5rem; }
.status td:first-child { color: #6b7e83; width: 40%; }
@media (max-width: 540px) { .row { grid-template-columns: 1fr; gap: .25rem; } }
</style>
</head><body>
<header>
  <h1>pool-temp admin</h1>
  <p>Edit settings without reflashing. Saves to NVS; takes effect on the next sample.</p>
</header>
<main>
)HTML";

  if (saved) html += "<div class=\"saved\">Saved.</div>\n";

  html += "<section class=\"status\"><h2>Status</h2><table>";
  html += "<tr><td>WiFi</td><td>" + esc(g_telemetry.wifi_ssid) + " &middot; " + esc(g_telemetry.wifi_ip)
        + " &middot; " + String(g_telemetry.wifi_rssi) + " dBm</td></tr>";
  html += "<tr><td>Uptime</td><td>" + String(g_telemetry.boot_seconds) + " s</td></tr>";
  html += "<tr><td>Sensors found</td><td>" + String(g_telemetry.sensor_count) + "</td></tr>";
  html += "<tr><td>Last temp</td><td>" + String(g_telemetry.last_temp_f, 2) + " &deg;F &middot; "
        + String((millis() - g_telemetry.last_sample_ms) / 1000) + " s ago</td></tr>";
  html += "<tr><td>POSTs OK / failed</td><td>" + String(g_telemetry.posts_ok) + " / "
        + String(g_telemetry.posts_failed) + "</td></tr>";
  html += "</table></section>";

  html += "<form method=\"post\" action=\"/save\">";

  html += "<section><h2>Endpoints</h2>";
  html += "<div class=\"row\"><label>Primary URL<span class=\"hint\">tried first; 2xx = success</span></label>"
          "<input name=\"endpoint_primary\" value=\"" + esc(g_config.endpoint_primary) + "\"></div>";
  html += "<div class=\"row\"><label>Fallback URL<span class=\"hint\">tried if primary fails; blank to skip</span></label>"
          "<input name=\"endpoint_fallback\" value=\"" + esc(g_config.endpoint_fallback) + "\"></div>";
  html += "<div class=\"row\"><label>API key<span class=\"hint\">sent as X-API-Key</span></label>"
          "<input name=\"api_key\" value=\"" + esc(g_config.api_key) + "\"></div>";
  html += "<div class=\"row\"><label>Device label<span class=\"hint\">tag included in payload</span></label>"
          "<input name=\"device_label\" value=\"" + esc(g_config.device_label) + "\"></div>";
  html += "</section>";

  html += "<section><h2>Sampling</h2>";
  html += "<div class=\"row\"><label>Period (seconds)<span class=\"hint\">how often we sample + POST</span></label>"
          "<input type=\"number\" min=\"5\" name=\"sample_seconds\" value=\""
        + String(g_config.sample_period_ms / 1000) + "\"></div>";
  html += "<div class=\"row\"><label>Min valid &deg;F<span class=\"hint\">readings below this are dropped</span></label>"
          "<input type=\"number\" step=\"0.1\" name=\"min_f\" value=\""
        + String(g_config.min_valid_f, 1) + "\"></div>";
  html += "<div class=\"row\"><label>Max valid &deg;F<span class=\"hint\">readings above this are dropped</span></label>"
          "<input type=\"number\" step=\"0.1\" name=\"max_f\" value=\""
        + String(g_config.max_valid_f, 1) + "\"></div>";
  html += "<div class=\"row\"><label>Primary sensor ROM<span class=\"hint\">16 hex chars; blank = first enumerated</span></label>"
          "<input name=\"primary_addr\" value=\"" + esc(g_config.primary_addr) + "\"></div>";
  html += "</section>";

  html += "<section><h2>Auth</h2>";
  html += "<div class=\"row\"><label>Admin user</label>"
          "<input name=\"admin_user\" value=\"" + esc(g_config.admin_user) + "\"></div>";
  html += "<div class=\"row\"><label>Admin password</label>"
          "<input name=\"admin_pass\" value=\"" + esc(g_config.admin_pass) + "\"></div>";
  html += "<div class=\"row\"><label>OTA password<span class=\"hint\">used by PlatformIO; takes effect after reboot</span></label>"
          "<input name=\"ota_password\" value=\"" + esc(g_config.ota_password) + "\"></div>";
  html += "</section>";

  html += "<div class=\"actions\">"
          "<button type=\"submit\">Save</button>"
          "<button type=\"button\" class=\"alt\" "
          "onclick=\"if (confirm('Reboot the device?')) fetch('/reboot',{method:'POST'}).then(()=>alert('rebooting'));\">"
          "Reboot device</button>"
          "</div>";
  html += "</form>";
  html += "</main></body></html>";
  return html;
}

// ---------- handlers ----------
static void handleRoot() {
  if (!requireAuth()) return;
  bool saved = server.arg("saved") == "1";
  server.send(200, "text/html; charset=utf-8", formHtml(saved));
}

static void handleSave() {
  if (!requireAuth()) return;
  if (server.hasArg("endpoint_primary"))  g_config.endpoint_primary  = server.arg("endpoint_primary");
  if (server.hasArg("endpoint_fallback")) g_config.endpoint_fallback = server.arg("endpoint_fallback");
  if (server.hasArg("api_key"))           g_config.api_key           = server.arg("api_key");
  if (server.hasArg("device_label"))      g_config.device_label      = server.arg("device_label");
  if (server.hasArg("sample_seconds")) {
    uint32_t s = server.arg("sample_seconds").toInt();
    if (s < 5) s = 5;
    g_config.sample_period_ms = s * 1000UL;
  }
  if (server.hasArg("min_f"))             g_config.min_valid_f       = server.arg("min_f").toFloat();
  if (server.hasArg("max_f"))             g_config.max_valid_f       = server.arg("max_f").toFloat();
  if (server.hasArg("primary_addr"))      g_config.primary_addr      = server.arg("primary_addr");
  if (server.hasArg("admin_user"))        g_config.admin_user        = server.arg("admin_user");
  if (server.hasArg("admin_pass"))        g_config.admin_pass        = server.arg("admin_pass");
  if (server.hasArg("ota_password"))      g_config.ota_password      = server.arg("ota_password");
  saveConfig(g_config);
  Serial.println("[admin] config saved");
  server.sendHeader("Location", "/?saved=1");
  server.send(303, "text/plain", "");
}

static void handleStatus() {
  String j = "{";
  j += "\"uptime_s\":"           + String(g_telemetry.boot_seconds) + ",";
  j += "\"sensors\":"            + String(g_telemetry.sensor_count) + ",";
  j += "\"last_temp_f\":"        + String(g_telemetry.last_temp_f, 2) + ",";
  j += "\"last_sample_age_s\":"  + String((millis() - g_telemetry.last_sample_ms) / 1000) + ",";
  j += "\"posts_ok\":"           + String(g_telemetry.posts_ok) + ",";
  j += "\"posts_failed\":"       + String(g_telemetry.posts_failed) + ",";
  j += "\"wifi_ssid\":\""        + g_telemetry.wifi_ssid + "\",";
  j += "\"wifi_ip\":\""          + g_telemetry.wifi_ip + "\",";
  j += "\"wifi_rssi\":"          + String(g_telemetry.wifi_rssi);
  j += "}";
  server.send(200, "application/json", j);
}

static void handleReboot() {
  if (!requireAuth()) return;
  server.send(200, "text/plain", "rebooting");
  delay(200);
  ESP.restart();
}

// ---------- public ----------
void adminBegin() {
  server.on("/",       HTTP_GET,  handleRoot);
  server.on("/save",   HTTP_POST, handleSave);
  server.on("/status", HTTP_GET,  handleStatus);
  server.on("/reboot", HTTP_POST, handleReboot);
  server.begin();
  Serial.println("[admin] http://pool-temp.local/  (and the device's IP)");
}

void adminLoop() {
  server.handleClient();
}

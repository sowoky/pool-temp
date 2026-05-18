#include "config.h"
#include <Preferences.h>

PoolConfig g_config;

static const char* NS = "pool-temp";

void loadConfig(PoolConfig& cfg) {
  Preferences p;
  p.begin(NS, /*readOnly=*/true);
  // ep_primary / ep_fallback are the legacy key names; we now treat them
  // both as "always send" endpoints, but keep the NVS keys for upgrade
  // compatibility so existing devices don't lose their URLs.
  cfg.endpoint_1 = p.getString("ep_primary",  "https://www.montesanoclub.org/temps/update");
  cfg.endpoint_2 = p.getString("ep_fallback", "https://temp.kyro-labs.com/reading");
  cfg.api_key    = p.getString("api_key",     "dev-key");
  cfg.sample_period_ms  = p.getUInt  ("sample_ms",   60000);
  cfg.min_valid_f       = p.getFloat ("min_f",       0.0f);
  cfg.max_valid_f       = p.getFloat ("max_f",       130.0f);
  cfg.primary_addr      = p.getString("primary",     "");
  cfg.admin_user        = p.getString("au_user",     "admin");
  cfg.admin_pass        = p.getString("au_pass",     "changeme");
  cfg.ota_password      = p.getString("ota_pass",    "pool-ota");
  cfg.device_label      = p.getString("dev_label",   "pool-equip-shed");

  cfg.auto_update_enabled    = p.getBool  ("au_enabled", true);
  cfg.update_manifest_url    = p.getString("au_url",     "https://raw.githubusercontent.com/sowoky/pool-temp/main/website/static/firmware/latest.json");
  cfg.update_check_period_ms = p.getUInt  ("au_period",  3600000UL);   // 1h
  p.end();
}

void saveConfig(const PoolConfig& cfg) {
  Preferences p;
  p.begin(NS, /*readOnly=*/false);
  p.putString("ep_primary",  cfg.endpoint_1);
  p.putString("ep_fallback", cfg.endpoint_2);
  p.putString("api_key",     cfg.api_key);
  p.putUInt  ("sample_ms",   cfg.sample_period_ms);
  p.putFloat ("min_f",       cfg.min_valid_f);
  p.putFloat ("max_f",       cfg.max_valid_f);
  p.putString("primary",     cfg.primary_addr);
  p.putString("au_user",     cfg.admin_user);
  p.putString("au_pass",     cfg.admin_pass);
  p.putString("ota_pass",    cfg.ota_password);
  p.putString("dev_label",   cfg.device_label);

  p.putBool  ("au_enabled",  cfg.auto_update_enabled);
  p.putString("au_url",      cfg.update_manifest_url);
  p.putUInt  ("au_period",   cfg.update_check_period_ms);
  p.end();
}

#include "config.h"
#include <Preferences.h>

PoolConfig g_config;

static const char* NS = "pool-temp";

void loadConfig(PoolConfig& cfg) {
  Preferences p;
  p.begin(NS, /*readOnly=*/true);
  cfg.endpoint_primary  = p.getString("ep_primary",  "http://montesanoclub.org/temps/update");
  cfg.endpoint_fallback = p.getString("ep_fallback", "https://niece-tweet-flame.ngrok-free.dev/reading");
  cfg.api_key           = p.getString("api_key",     "dev-key");
  cfg.sample_period_ms  = p.getUInt  ("sample_ms",   60000);
  cfg.min_valid_f       = p.getFloat ("min_f",       0.0f);
  cfg.max_valid_f       = p.getFloat ("max_f",       130.0f);
  cfg.primary_addr      = p.getString("primary",     "");
  cfg.admin_user        = p.getString("au_user",     "admin");
  cfg.admin_pass        = p.getString("au_pass",     "changeme");
  cfg.ota_password      = p.getString("ota_pass",    "pool-ota");
  cfg.device_label      = p.getString("dev_label",   "pool-equip-shed");
  p.end();
}

void saveConfig(const PoolConfig& cfg) {
  Preferences p;
  p.begin(NS, /*readOnly=*/false);
  p.putString("ep_primary",  cfg.endpoint_primary);
  p.putString("ep_fallback", cfg.endpoint_fallback);
  p.putString("api_key",     cfg.api_key);
  p.putUInt  ("sample_ms",   cfg.sample_period_ms);
  p.putFloat ("min_f",       cfg.min_valid_f);
  p.putFloat ("max_f",       cfg.max_valid_f);
  p.putString("primary",     cfg.primary_addr);
  p.putString("au_user",     cfg.admin_user);
  p.putString("au_pass",     cfg.admin_pass);
  p.putString("ota_pass",    cfg.ota_password);
  p.putString("dev_label",   cfg.device_label);
  p.end();
}

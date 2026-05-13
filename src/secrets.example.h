// Copy this file to `secrets.h` and fill in real values.
// `secrets.h` is gitignored.
#pragma once

// WiFi networks the firmware will try at boot, in this order.
// Whichever is in range gets connected to. One firmware build works at home
// (DEV_*) and at the pool (FALLBACK_*) without recompiling.
static const char* DEV_SSID      = "your-home-wifi-ssid";
static const char* DEV_PASS      = "your-home-wifi-password";
static const char* FALLBACK_SSID = "pool-public";
static const char* FALLBACK_PASS = nullptr;   // open network -> nullptr; else "pwd"

# Forecast roadmap

The prophecy page is structurally honest about how rough the current
numbers are. Here's how we sharpen it.

## Phase 0 — what's shipped

- `/api/forecast` chains KHSV gridpoint forecast → corrected Monte Sano air
  → pool water via a single-`k` first-order thermal model.
- Ridge offset uses a default `-3.5°F` until we have ≥1 paired KHSV/PWS
  observation pair. Switches to median-of-paired as soon as we do.
- Pool `k` is fit from hourly water/air paired data with outlier trimming.
- All three sources are tagged in the JSON response (`source: "fit" | "default"`).

## Phase 1 — short term (days, no extra effort beyond letting time pass)

- [ ] Let `pws_history` accumulate at least 30 days for both stations
      (one backfill run + ongoing live ingestion).
- [ ] Let `outdoor_readings` source='nws' accumulate 7+ days alongside.
      Then `_paired_ms_offset()` should switch from "default" to "fit"
      automatically.
- [ ] Add an hourly poll of *KHSV* specifically (independent of the priority
      cascade) so we always have a paired sample to compare PWS against,
      even when WU is winning the cascade.

## Phase 2 — short term (a couple hours of work)

- [ ] Time-of-day offset table instead of a single median: bucket by hour
      and store `offset[0..23]`. Inversions are big at sunrise — a flat
      offset over-cools the morning forecast.
- [ ] Pump-off detector: rolling stdev on `pool_readings`. When σ < 0.05°F
      over a 10-min window, flag the rows; exclude them from `_fit_pool_k`.
- [ ] Cloud-cover adjustment: pull `shortForecast` from NWS, parse for
      "sunny" vs "cloudy", apply a multiplicative factor to `k` (sunny days
      should warm the pool faster).
- [ ] Wind adjustment: high wind days evaporate harder; `k` should be
      modestly higher on windy days. NWS gives `windSpeed` per period; use it.

## Phase 3 — medium term

- [ ] Multi-`k` thermal model (one for day, one for night) — diurnal heating
      from sun is fundamentally different from radiative cooling at night.
- [ ] Dew-point as a forecast input. On nights with very dry air, the pool
      cools faster through evaporation than the air-temperature gap implies.
- [ ] Backtest mode: replay the last 7 days through the forecaster and show
      the error histogram on the page. Lets us know if we're getting better.

## Phase 4 — nice-to-have

- [ ] Solar radiation model. KALHUNTS264 reports `solarRadiationHigh`. Pull
      it as an additional regressor.
- [ ] Pump-state estimator. If we ever wire a current sensor to the pump
      circuit (CLAUDE.md future), we can mark pump-on vs pump-off windows
      directly instead of inferring from σ.
- [ ] Migrate from NWS gridpoint to NDFD raw grid: gridpoint is interpolated
      to a single point, we can do better by averaging the 4 neighboring
      cells with our own elevation correction.

## Out of scope (for now)

- Replacing NWS with a paid commercial forecast (Tomorrow.io, WeatherKit).
  Free is fine until we know what the limits actually are.
- Multi-day pool prediction beyond the NWS forecast horizon. Pool inertia
  is high enough that "next week" depends on more than just the air
  forecast (it depends on rain dilution, pool refilling, etc.).

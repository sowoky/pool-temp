# Temperature research log

Living scratchpad for everything we know (and want to know) about how the
pool, the ridge air, and the valley air relate.

## Sources we use

| Source | What it is | Coverage we have | Coverage we *can* get |
|---|---|---|---|
| **DS18B20 on the PVC return** | Strap-mounted to the filter return line. The "pool water" reading. | starts the day the firmware came online (currently ~1 day of hourly data via `hourly_log`) | continuous from now on, ~1/min |
| **`montesanoclub.org/pool` scrape** | The public club site's water number. Same physical probe, but bounced through whatever middleware the club site is running. | continuous, currently the *primary* `pool_readings` source (firmware POSTs go to the club, we scrape it back) | as long as the club site exists and renders the temperature into the page HTML |
| **WU PWS `KALHUNTS560`** | Personal weather station on the ridge, ~⅓ mile from the pool. Reports every 5 min. | only current values until backfill is run | ~3 years of history (depending on the owner) via `/v2/pws/history/all` |
| **WU PWS `KALHUNTS264`** | Second ridge PWS, similar distance. | same | same |
| **NWS `KHSV`** | Huntsville International Airport ASOS, ~5.5 mi *off* the mountain and ~1700 ft *down*. The "official" Huntsville temperature. | ~1 week available via free endpoint | only ~7 days via NWS API. Deeper history would need Synoptic / NCEI |
| **NWS gridpoint forecast** | The NWS forecast for the point at the pool's lat/lon — though it's really an interpolation of the gridded forecast that covers ~2.5 km cells. | live | live |

## Which is "the Huntsville temperature"?

When someone says *"the forecast for Huntsville,"* they almost certainly mean
one of:

1. **The NWS daily forecast for the valley**, which is what gets read out on
   WAFF / WHNT / weather apps. Underlying data: the gridded forecast for
   downtown Huntsville (around 34.73, -86.59). This is what we pull via
   `api.weather.gov/points/{lat},{lon}/forecast`.
2. **The current temperature at KHSV airport**, which is what airlines/AviationWX
   use. Underlying data: the ASOS at the airport, observed each minute.
3. **Whatever Google says when you type "huntsville al temp"**, which uses
   weather.com's own grid (proprietary, not public).

For our purposes we use **(1) + (2)**:
- (2) gives us a true, sensor-backed valley temperature to anchor offsets.
- (1) gives us a forward-looking number to feed into the prophecy.

**KHSV is the right anchor for "Huntsville"** because (a) it's the longest-
running sensor in the city, (b) it's the dataset everyone's weather model
trains on, and (c) it has the smallest siting bias of any of our candidates.

## Why Monte Sano runs colder than Huntsville

The pool sits at ~1750 ft. KHSV sits at ~620 ft. The dry adiabatic lapse rate
is ~5.4°F per 1000 ft, the saturated rate ~3.3°F per 1000 ft. So we'd expect
roughly **4–6°F cooler** at the pool on a dry day, plus extra effects:

- **Inversions** (cool nights, clear sky, no wind): the valley pools cold air;
  the mountain can actually be *warmer* overnight in winter. Inverts the sign
  of the delta.
- **Insolation**: on a sunny summer afternoon the ridge gets the same sun but
  cools faster because winds aloft are higher.
- **Sun angle**: mid-day, the ridge gets less shadow from buildings, so the
  ridge PWS may *over*read in summer afternoons depending on solar shielding.
- **Wind canalization**: the gap east of the mountain funnels wind, which can
  produce a 5–10°F cold pocket on the ridge in winter cold fronts.

The user's note ("up to 10°F cooler sometimes") matches the upper end of the
inversion / cold-front cases. The mean is closer to 3–5°F.

## What we want to figure out

1. **Is the PWS pair drifting?** If `KALHUNTS560 − KALHUNTS264` has a stable
   mean far from zero, one of them is mis-sited. If σ is large, one of them
   has poor solar shielding.
2. **What's the *real* lapse?** Use paired hourly data to fit a regression of
   `(MS_air − KHSV)` vs. time-of-day, cloud cover, wind speed. The single-
   number "offset" is the median; the residual is where the interesting
   weather lives.
3. **What's the pool-air coupling `k`?** First-order thermal mass model:
   `dT/dt = k * (air − pool)`. `k` depends on pool surface area, depth, wind,
   sun, pump duty. Once we have 7+ days of high-resolution water history we
   can fit it cleanly.
4. **Pump-off detection?** Pool reads will drift wildly when the pump is off
   (stagnant pipe). Future work: detect pump-off windows from the standard
   deviation of consecutive readings, mask them out of the model fit.

## Empirical findings from the first 30-day backfill (2026-04-14 → 2026-05-14)

Paired observations: 491 (sample density limited by hourly DB join, not WU coverage).

| Stat | Value |
|---|---|
| mean signed Δ (560 − 264) | −0.07 °F |
| median signed Δ | −0.40 °F |
| stdev | 1.93 °F |
| min / max | −6.70 °F / +8.70 °F |
| mean &#124;Δ&#124; | 1.45 °F |

**The mean is misleading. The two stations swap which one is hotter by time of day:**

| UTC hour (local CDT = UTC−5) | Mean Δ (560 − 264) |
|---|---|
| 14:00 (09:00 CDT) — late morning | **+1.58 °F** |
| 15:00 (10:00 CDT) | **+2.79 °F** ← 560 hottest |
| 16:00 (11:00 CDT) | +2.62 °F |
| 17:00 (12:00 CDT) — noon | +2.61 °F |
| 18:00 (13:00 CDT) | +1.02 °F |
| 19:00 (14:00 CDT) | −1.10 °F ← roles flip |
| 20:00 (15:00 CDT) — mid-afternoon | **−2.58 °F** ← 264 hottest |
| 21:00 (16:00 CDT) | −1.69 °F |
| 22:00 (17:00 CDT) | −1.40 °F |
| overnight (00:00 – 13:00 UTC) | within ±0.6 °F (close to noise) |

Interpretation: **KALHUNTS560 sees morning sun. KALHUNTS264 sees afternoon sun.**
Both stations are direct-radiation biased; whichever has the sun on it is
~2°F hotter than the other. At night, they agree (no solar bias to disagree
about). The signed mean averages to ~0 only because the two biases roughly
cancel.

**This means averaging them is *more* correct than picking one**, for the
specific reason that the two biases offset each other. We get one "warm
biased" station and one "cool biased" station at any given afternoon hour,
and the average is close to truth.

A better fix would be picking *the shaded one* per hour:
- Morning (10–13 CDT): prefer KALHUNTS264 (the cooler, shaded one)
- Afternoon (15–18 CDT): prefer KALHUNTS560 (the cooler, shaded one)

A small heuristic for the cascade order would be: pick the station whose
recent (last hour) reading is the *lower* of the two — it's the one not
currently being baked.

## Why averaging both PWS stations is probably correct

Until we know one is bad, the noise-reduction of averaging two ~independent
sensors is √2. The cost is the worst case where one is biased and pulls the
average. The fix is the **`/stations` page** — once we can show the signed
bias is small (< 0.5°F), averaging is strictly better than picking one.

If signed bias is large, we should switch to "prefer the cooler one for
afternoons, prefer the warmer one for nights" (since the warmer one is
likely better shielded in the cold cases, and the cooler one less sun-
biased).

## Open questions

- **Do PWS stations report when the owner takes them offline?** If a station
  is reporting yesterday's value all day, our average is poisoned. Need to
  add a freshness check (drop obs older than ~30 min).
- **What's the cleanest way to detect pump-off?** Candidate: rolling stdev of
  the last 10 readings. When the pump's on, water exchanges every cycle and
  σ ≈ 0.1°F per minute. When it's off, σ collapses to sensor noise (~0.05°F).
  A drop *plus* a slow drift toward ambient = pump-off.
- **Should we forecast more than 7 days?** NWS gives ~7. After that we'd need
  to chain on climatology or a paid forecast feed. Probably not worth it.

## Models in play

| Model | Equation | Where it lives |
|---|---|---|
| Monte Sano air offset | `MS_air ≈ KHSV + offset` | `forecast._paired_ms_offset()` |
| Pool thermal lag | `pool[t+Δ] = pool[t] + k·(air[t] − pool[t])` | `forecast._fit_pool_k()` |
| Station bias | `bias = mean(KALHUNTS560 − KALHUNTS264)` | `/api/stations` |

All three start with a sensible default and switch to a fit value as soon
as we have ≥30 paired samples. The `/forecast` page surfaces which source
each one is currently using.

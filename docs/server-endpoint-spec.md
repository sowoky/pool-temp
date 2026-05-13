# Pool temperature ingestion endpoint

Hand-off spec for the web admin. Describes what the ESP32 in the pool
equipment shed POSTs to the server, on what cadence, and what the server
needs to do to accept it.

## TL;DR

A small ESP32 in the pool equipment shed POSTs a JSON body to a single URL
every 60 seconds. If the server returns any 2xx, the firmware considers the
reading delivered. Anything else, the firmware fails over to its backup URL
and tries again. So the only thing the server needs to do correctly:

- accept `POST <your URL>`
- validate the `X-API-Key` header
- parse the JSON
- persist it
- return `200 OK` (any 2xx is fine)

## Endpoint

| | |
|---|---|
| Method | `POST` |
| URL (preferred) | `http://montesanoclub.org/temps/update` |
| Content-Type | `application/json` |
| Authentication | header `X-API-Key: dev-key` |
| Body | see below |
| Expected response | any 2xx with any body (JSON is nice but not required) |
| Cadence | one POST every ~60 seconds |
| Source IP | the ESP32&rsquo;s WiFi IP &mdash; varies; don&rsquo;t IP-allowlist |

`dev-key` is a placeholder. Rotate it whenever you want &mdash; just let me
know the new value and I&rsquo;ll update the firmware in step.

## Request body

```json
{
  "sensors": [
    {"addr": "280D0E8A060000E5", "temp_f": 78.42},
    {"addr": "288D578B060000E6", "temp_f": 78.51}
  ],
  "temp_f": 78.42
}
```

Field reference:

- `temp_f` (top-level): the &ldquo;primary&rdquo; reading in Fahrenheit. This
  is what you&rsquo;d display as &ldquo;the pool temp.&rdquo; It&rsquo;s
  whichever of the multiple probes the firmware picked first &mdash; same
  one cycle to cycle as long as the sensors stay plugged in.
- `sensors`: array of per-probe readings. Each has:
  - `addr`: 16-hex-char unique DS18B20 ROM address (a 64-bit serial baked
    into each chip at the factory). Use this to tell sensors apart if we
    ever instrument more than one location.
  - `temp_f`: that sensor&rsquo;s reading in Fahrenheit.

The firmware bounds-checks readings between 0&deg;F and 130&deg;F before
sending. You won&rsquo;t see disconnected-sensor values (`-127`) or
absurdities in the payload.

## Validation hints

- If `temp_f` is missing or not a number: reject with `400`.
- If `X-API-Key` is missing or wrong: reject with `401`.
- If JSON parse fails: reject with `400`.
- Otherwise persist (timestamp it server-side) and return `200`.

Returning `4xx`/`5xx` makes the firmware fail over to its backup URL, so
correctness matters more than performance &mdash; it&rsquo;s better to take
500ms and return `200` than to return `503` because the DB is slow.

## Suggested server-side shape (totally up to you)

```sql
CREATE TABLE pool_readings (
    id         SERIAL PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    primary_f  REAL NOT NULL,
    raw_json   JSONB NOT NULL,
    remote_ip  INET
);

CREATE TABLE pool_sensor_readings (
    reading_id INT NOT NULL REFERENCES pool_readings(id) ON DELETE CASCADE,
    addr       TEXT NOT NULL,
    temp_f     REAL NOT NULL
);
```

Keep the raw JSON. The firmware payload may grow (humidity, pump-status,
etc.) and you don&rsquo;t want to keep migrating columns.

## Failover behavior (FYI, you don&rsquo;t have to handle it)

The firmware tries this list in order:

1. `http://montesanoclub.org/temps/update`  &larr; you
2. `https://niece-tweet-flame.ngrok-free.dev/reading`  &larr; my fallback

Both addresses receive the same payload with the same `X-API-Key` header.
Once your endpoint returns 2xx reliably, the fallback never gets hit.

I can pull the fallback out of the firmware entirely once we&rsquo;re
confident yours is solid. Not urgent.

## Frequency &amp; volume

- 1 POST per minute, 24/7 &asymp; 43,200 POSTs / month
- Payload size &lt; 200 bytes per request
- No bursts, no retries beyond the failover step (next sample is in 60s)
- Probe goes offline whenever the equipment shed loses power; just stops
  POSTing &mdash; no funny &ldquo;catch up&rdquo; behavior on reconnect

## Live reference

You can hit `https://niece-tweet-flame.ngrok-free.dev/api/current` right now
to see the format of stored readings my fallback server holds. Same JSON
shape, with a couple of extra fields the server adds on receipt
(`_received_at`, `_remote`). Useful as a sanity check while you&rsquo;re
implementing.

## Contact

Questions, key rotation, or schema tweaks &mdash; ping Kyle.

"""Pool temp website + ingestion endpoint.

Routes:
    GET  /                    -- home page
    GET  /temperature         -- historical chart page
    GET  /api/current         -- current pool + outdoor temps
    GET  /api/history         -- pool + outdoor history (?range=24h|7d|30d)
    POST /reading             -- ESP32 ingestion (X-API-Key required)
    GET  /healthz             -- 200 OK for monitoring

Run dev:   python app.py
Run prod:  waitress-serve --listen=0.0.0.0:18080 app:app
"""

import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

import db
import weather

API_KEY               = os.environ.get("POOL_API_KEY", "dev-key")
WEATHER_POLL_SECONDS  = int(os.environ.get("WEATHER_POLL_SECONDS", "600"))   # 10 min
PORT                  = int(os.environ.get("PORT", "18080"))

app = Flask(__name__)
db.init()


# ---------------------------------------------------------------- background
def _weather_loop():
    while True:
        try:
            result = weather.fetch_outdoor()
            if result is not None:
                temp_f, source, station_id, raw = result
                db.insert_outdoor_reading(source, temp_f, station_id, raw)
                print(f"[weather] {source}/{station_id or '-'}: {temp_f:.1f}F")
            else:
                print("[weather] all sources failed this cycle")
        except Exception as e:
            print(f"[weather] loop error: {e}")
        time.sleep(WEATHER_POLL_SECONDS)


def _start_weather_thread():
    t = threading.Thread(target=_weather_loop, daemon=True, name="weather-poll")
    t.start()


# kick off background poller; daemon so it dies with the process
_start_weather_thread()


# ---------------------------------------------------------------- helpers
def _age_seconds(iso: str) -> int:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - dt).total_seconds())
    except ValueError:
        return -1


# ---------------------------------------------------------------- pages
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/temperature")
def temperature():
    return render_template("temperature.html")


# ---------------------------------------------------------------- api
@app.route("/api/current")
def api_current():
    pool = db.latest_pool_reading()
    outdoor = db.latest_outdoor_reading()
    return jsonify({
        "pool":    {
            **pool,
            "age_seconds": _age_seconds(pool["ts"]),
        } if pool else None,
        "outdoor": {
            **outdoor,
            "age_seconds": _age_seconds(outdoor["ts"]),
        } if outdoor else None,
    })


@app.route("/api/history")
def api_history():
    range_key = request.args.get("range", "24h")
    since = db.range_to_since(range_key)
    return jsonify({
        "range":   range_key,
        "pool":    db.pool_history(since),
        "outdoor": db.outdoor_history(since),
    })


# ---------------------------------------------------------------- ingestion
@app.route("/reading", methods=["POST"])
def reading():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "bad api key"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "temp_f" not in payload:
        return jsonify({"error": "expected json with temp_f"}), 400

    remote = request.headers.get("X-Forwarded-For") or request.remote_addr
    reading_id = db.insert_pool_reading(payload, remote)

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{ts}] reading#{reading_id} from {remote}: {payload.get('temp_f')}F")
    return jsonify({"ok": True, "id": reading_id, "received_at": ts})


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"pool-temp website -> http://0.0.0.0:{PORT}")
    print(f"  weather poll every {WEATHER_POLL_SECONDS}s")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

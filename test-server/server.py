"""Stand-in for the pool website endpoint.

Run on your laptop while the real admin endpoint is pending. The ESP32
points at http://<this-laptop's LAN IP>:8080/reading and POSTs JSON.

Usage:
    python server.py            # listens on 0.0.0.0:8080
    python server.py 9000       # custom port
"""

import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = "dev-key"
readings: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/readings":
            self._send(200, {"count": len(readings), "readings": readings[-50:]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/reading":
            self._send(404, {"error": "not found"})
            return

        if self.headers.get("X-API-Key") != API_KEY:
            self._send(401, {"error": "bad api key"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            self._send(400, {"error": f"bad json: {e}"})
            return

        ts = datetime.now().isoformat(timespec="seconds")
        body["_received_at"] = ts
        body["_remote"] = self.client_address[0]
        readings.append(body)

        primary = body.get("temp_f")
        sensors = body.get("sensors") or []
        summary = f"primary={primary}"
        if sensors:
            summary += "  sensors=[" + ", ".join(
                f"{s.get('addr','?')[-4:]}:{s.get('temp_f')}" for s in sensors
            ) + "]"
        print(f"[{ts}] {self.client_address[0]} -> {summary}")

        self._send(200, {"ok": True, "received_at": ts})

    def log_message(self, fmt: str, *args) -> None:
        # quiet the default per-request log; we print our own line in do_POST
        return


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"pool-temp test endpoint listening on http://0.0.0.0:{port}")
    print(f"  POST /reading        (X-API-Key: {API_KEY})")
    print(f"  GET  /readings       last 50 received")
    print("Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        srv.server_close()


if __name__ == "__main__":
    main()

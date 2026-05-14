// Shared script: hydrates the temp cards on any page that includes them.

(function () {
  const REFRESH_MS = 30 * 1000;

  function fmtTempF(f) {
    if (f === null || f === undefined || Number.isNaN(f)) return "—";
    return `${Number(f).toFixed(1)}°F`;
  }

  function fmtAge(seconds) {
    if (seconds === undefined || seconds === null || seconds < 0) return "—";
    if (seconds < 60)   return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
    if (seconds < 86400) {
      const h = Math.floor(seconds / 3600);
      const m = Math.round((seconds % 3600) / 60);
      return m ? `${h}h ${m}m ago` : `${h}h ago`;
    }
    return `${Math.floor(seconds / 86400)}d ago`;
  }

  function bind(name, value) {
    document.querySelectorAll(`[data-bind="${name}"]`).forEach((el) => {
      el.textContent = value;
    });
  }

  async function refresh() {
    try {
      const r = await fetch("/api/current", { cache: "no-store" });
      if (!r.ok) throw new Error(`status ${r.status}`);
      const data = await r.json();

      // ---- pool ----
      if (data.pool) {
        const t = data.pool.temp_f;
        bind("pool.temp", fmtTempF(t));
        bind("pool.temp-small", fmtTempF(t));
        const sensorCount = (data.pool.sensors || []).length;
        // The reading either came from the ESP32 (sensors[] populated) or
        // from our scrape of the club site (sensors[] empty). Show the
        // source so it's obvious which.
        let label;
        if (sensorCount === 0 && data.pool.source && data.pool.source.startsWith("scrape:")) {
          label = "via club site";
        } else {
          label = sensorCount === 1 ? "1 sensor" : `${sensorCount} sensors`;
        }
        bind("pool.meta", `${fmtAge(data.pool.age_seconds)} · ${label}`);
        bind("pool.ago", fmtAge(data.pool.age_seconds));
      } else {
        bind("pool.temp", "—");
        bind("pool.temp-small", "—");
        bind("pool.meta", "No readings yet");
        bind("pool.ago", "—");
      }

      // ---- outdoor ----
      if (data.outdoor) {
        const t = data.outdoor.temp_f;
        bind("outdoor.temp", fmtTempF(t));
        bind("outdoor.temp-small", fmtTempF(t));
        const src = data.outdoor.source || "weather";
        const station = data.outdoor.station_id ? ` · ${data.outdoor.station_id}` : "";
        bind("outdoor.meta", `${fmtAge(data.outdoor.age_seconds)} · ${src}${station}`);
      } else {
        bind("outdoor.temp", "—");
        bind("outdoor.temp-small", "—");
        bind("outdoor.meta", "No outdoor data yet");
      }
    } catch (err) {
      console.warn("refresh failed:", err);
    }
  }

  refresh();
  setInterval(refresh, REFRESH_MS);
})();

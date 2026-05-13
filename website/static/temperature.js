// /temperature page: history chart + range buttons + summary stats.

(function () {
  if (typeof Chart === "undefined") return;

  const ctx = document.getElementById("tempChart");
  if (!ctx) return;

  let chart;
  let currentRange = "24h";

  // honor ?focus=pool|outdoor for the future, currently both lines always shown
  const params = new URLSearchParams(window.location.search);
  const initialFocus = params.get("focus");

  function tickUnit(range) {
    if (range === "24h") return "hour";
    if (range === "7d")  return "day";
    return "day";
  }

  function statOf(arr, key) {
    if (!arr.length) return { min: null, max: null, avg: null };
    const vals = arr.map((p) => p[key]).filter((v) => typeof v === "number");
    if (!vals.length) return { min: null, max: null, avg: null };
    const sum = vals.reduce((a, b) => a + b, 0);
    return { min: Math.min(...vals), max: Math.max(...vals), avg: sum / vals.length };
  }

  function fmt(v) {
    return v === null || v === undefined ? "—" : `${v.toFixed(1)}°F`;
  }

  function setStats(pool, outdoor) {
    const ps = statOf(pool, "temp_f");
    const os = statOf(outdoor, "temp_f");
    document.querySelector('[data-stat="pool.min"]').textContent = fmt(ps.min);
    document.querySelector('[data-stat="pool.max"]').textContent = fmt(ps.max);
    document.querySelector('[data-stat="pool.avg"]').textContent = fmt(ps.avg);
    document.querySelector('[data-stat="outdoor.min"]').textContent = fmt(os.min);
    document.querySelector('[data-stat="outdoor.max"]').textContent = fmt(os.max);
    document.querySelector('[data-stat="outdoor.avg"]').textContent = fmt(os.avg);
  }

  async function load(range) {
    const meta = document.getElementById("range-meta");
    meta.textContent = "Loading…";
    try {
      const r = await fetch(`/api/history?range=${encodeURIComponent(range)}`, { cache: "no-store" });
      const data = await r.json();

      const pool    = (data.pool    || []).map((p) => ({ x: p.ts, temp_f: p.temp_f }));
      const outdoor = (data.outdoor || []).map((p) => ({ x: p.ts, temp_f: p.temp_f }));

      meta.textContent = `${pool.length} pool · ${outdoor.length} outdoor samples`;
      setStats(pool, outdoor);

      const datasets = [
        {
          label: "Pool",
          data: pool.map((p) => ({ x: p.x, y: p.temp_f })),
          borderColor: getComputedStyle(document.documentElement).getPropertyValue("--pool").trim() || "#15808a",
          backgroundColor: "rgba(21,128,138,.12)",
          tension: 0.25,
          pointRadius: 0,
          borderWidth: 2,
          fill: true,
        },
        {
          label: "Outdoor",
          data: outdoor.map((p) => ({ x: p.x, y: p.temp_f })),
          borderColor: getComputedStyle(document.documentElement).getPropertyValue("--air").trim() || "#e89b2b",
          backgroundColor: "rgba(232,155,43,.10)",
          tension: 0.25,
          pointRadius: 0,
          borderWidth: 2,
          fill: false,
        },
      ];

      if (chart) chart.destroy();
      chart = new Chart(ctx, {
        type: "line",
        data: { datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { position: "top" },
            tooltip: {
              callbacks: {
                label: (c) => `${c.dataset.label}: ${c.parsed.y.toFixed(2)}°F`,
              },
            },
          },
          scales: {
            x: {
              type: "time",
              time: { unit: tickUnit(range) },
              grid: { color: "rgba(0,0,0,.06)" },
            },
            y: {
              title: { display: true, text: "°F" },
              grid: { color: "rgba(0,0,0,.06)" },
            },
          },
        },
      });
    } catch (err) {
      meta.textContent = `Error: ${err.message}`;
    }
  }

  document.querySelectorAll(".range-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentRange = btn.dataset.range;
      document.querySelectorAll(".range-btn").forEach((b) => {
        b.setAttribute("aria-pressed", b === btn ? "true" : "false");
      });
      load(currentRange);
    });
  });

  load(currentRange);
  setInterval(() => load(currentRange), 60 * 1000);
})();

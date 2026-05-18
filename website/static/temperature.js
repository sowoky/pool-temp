// /temperature — pool + air history chart.
// Tooltip: hovering shows a formatted timestamp + both series at that point.

(function () {
  if (typeof Chart === "undefined") return;

  const ctx = document.getElementById("tempChart");
  if (!ctx) return;

  // ---- dark-theme defaults so we don't repeat ourselves ----
  Chart.defaults.color = "rgba(241, 234, 212, .72)";
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.borderColor = "rgba(187, 229, 240, .12)";

  // colors come from CSS vars so the chart and the page stay in sync.
  const css = getComputedStyle(document.documentElement);
  const COL_POOL    = (css.getPropertyValue("--pool") || "#38d6df").trim();
  const COL_POOL_SF = "rgba(56, 214, 223, .14)";
  const COL_AIR     = (css.getPropertyValue("--air")  || "#ff8a3d").trim();

  let chart;
  let currentRange = "24h";

  function tickUnit(range) {
    if (range === "24h") return "hour";
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

  function fmtTooltipTitle(items) {
    if (!items || !items.length) return "";
    const ts = items[0].parsed.x;
    return new Date(ts).toLocaleString("en-US", {
      weekday: "short",
      month:   "short",
      day:     "numeric",
      hour:    "numeric",
      minute:  "2-digit",
    });
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
          borderColor: COL_POOL,
          backgroundColor: COL_POOL_SF,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: COL_POOL,
          pointHoverBorderColor: "rgba(7,23,28,1)",
          pointHoverBorderWidth: 2,
          borderWidth: 2.4,
          fill: true,
        },
        {
          label: "Outdoor air",
          data: outdoor.map((p) => ({ x: p.x, y: p.temp_f })),
          borderColor: COL_AIR,
          backgroundColor: "rgba(255, 138, 61, .08)",
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: COL_AIR,
          pointHoverBorderColor: "rgba(7,23,28,1)",
          pointHoverBorderWidth: 2,
          borderWidth: 2.4,
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
          animation: { duration: 350 },
          interaction: { mode: "index", intersect: false, axis: "x" },
          plugins: {
            legend: {
              position: "top",
              align: "end",
              labels: { boxWidth: 14, boxHeight: 2, padding: 16, color: "rgba(241,234,212,.85)" },
            },
            tooltip: {
              backgroundColor: "rgba(2, 9, 13, .92)",
              borderColor: "rgba(212, 183, 94, .25)",
              borderWidth: 1,
              titleColor: "#f1ead4",
              bodyColor: "#f1ead4",
              titleFont: { weight: 600, size: 12 },
              bodyFont: { family: "ui-monospace, SFMono-Regular, monospace", size: 12 },
              padding: 10,
              caretSize: 6,
              displayColors: true,
              boxPadding: 4,
              callbacks: {
                title: fmtTooltipTitle,
                label: (c) => `  ${c.dataset.label}: ${c.parsed.y.toFixed(2)}°F`,
              },
            },
          },
          scales: {
            x: {
              type: "time",
              time: { unit: tickUnit(range) },
              grid:   { color: "rgba(187, 229, 240, .06)" },
              ticks:  { color: "rgba(241, 234, 212, .55)" },
              border: { color: "rgba(187, 229, 240, .12)" },
            },
            y: {
              title: { display: true, text: "°F", color: "rgba(241, 234, 212, .55)" },
              grid:   { color: "rgba(187, 229, 240, .06)" },
              ticks:  { color: "rgba(241, 234, 212, .55)" },
              border: { color: "rgba(187, 229, 240, .12)" },
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

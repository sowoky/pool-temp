// /stations — side-by-side PWS analysis.

(function () {
  if (typeof Chart === "undefined") return;

  Chart.defaults.color = "rgba(241, 234, 212, .72)";
  Chart.defaults.borderColor = "rgba(187, 229, 240, .12)";

  const css = getComputedStyle(document.documentElement);
  const COL_560 = (css.getPropertyValue("--pws-560") || "#38d6df").trim();
  const COL_264 = (css.getPropertyValue("--pws-264") || "#f5cb5c").trim();
  const COL_GOLD = (css.getPropertyValue("--rune-gold") || "#d4b75e").trim();

  let stChart, dChart;
  let currentRange = "30d";

  function fmt(v, digits = 1, unit = "°F") {
    return v === null || v === undefined || Number.isNaN(v)
      ? "—"
      : `${Number(v).toFixed(digits)}${unit}`;
  }
  function fmtSigned(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const s = Number(v) >= 0 ? "+" : "−";
    return `${s}${Math.abs(v).toFixed(2)}°F`;
  }
  function bind(name, val) {
    document.querySelectorAll(`[data-bind="${name}"]`).forEach((el) => el.textContent = val);
  }
  function fmtTooltipTitle(items) {
    if (!items || !items.length) return "";
    return new Date(items[0].parsed.x).toLocaleString("en-US", {
      weekday: "short", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit",
    });
  }

  function describeRange(rangeKey) {
    return { "7d": "7 days", "30d": "30 days", "90d": "90 days",
             "1y": "1 year",  "2y": "2 years" }[rangeKey] || rangeKey;
  }

  function tickUnit(range) {
    if (range === "7d") return "day";
    if (range === "30d") return "day";
    return "week";
  }

  function writeVerdict(stats, s550n, s264n, totalPaired) {
    const el = document.querySelector('[data-bind="verdict.body"]');
    if (!el) return;

    if (totalPaired < 24) {
      el.innerHTML = `
        Not enough paired observations yet to be confident — we have only
        <strong>${totalPaired}</strong> overlapping samples on file. Once
        the backfill catches up (a few thousand pairs minimum), we'll fit a
        signed offset and a per-station drift estimate.
      `;
      return;
    }

    const meanAbs = stats.abs_mean ?? null;
    const mean    = stats.mean ?? null;
    const std     = stats.stdev ?? null;
    const drift   = (meanAbs ?? 0) >= 1.0;
    const skew    = Math.abs(mean ?? 0) >= 0.4;

    let body = "";
    if (!drift && !skew) {
      body = `
        The stations agree closely — mean |delta| is <strong>${fmt(meanAbs, 2)}</strong>
        and the signed bias is <strong>${fmtSigned(mean)}</strong>.
        Averaging the two is fine; either as a sole source is fine. Disagreement
        is noise-level, not a systematic bias.
      `;
    } else if (skew && !drift) {
      const high = mean > 0 ? "KALHUNTS560" : "KALHUNTS264";
      const low  = mean > 0 ? "KALHUNTS264" : "KALHUNTS560";
      body = `
        ${high} reads consistently warmer than ${low} by
        <strong>${fmtSigned(mean)}</strong> (σ <strong>${fmt(std, 2)}</strong>).
        That's a real bias — probably siting (sun, building radiance, ground
        cover). For a single-source pick, lean ${low} as the cooler / more
        likely ambient. Or average and accept ~${fmt(Math.abs(mean) / 2, 1)} of slop.
      `;
    } else {
      // mean ≈ 0 but |delta| is big — classic sun-bias swap (two stations
      // catch sun at different times). Confirmed by the diurnal analysis
      // in docs/temperature-research.md: 560 gets morning sun, 264 gets
      // afternoon sun. Their biases roughly cancel, which is why averaging
      // them is still useful.
      body = `
        Mean signed delta is near zero (<strong>${fmtSigned(mean)}</strong>)
        but mean |delta| is big (<strong>${fmt(meanAbs, 2)}</strong>,
        σ <strong>${fmt(std, 2)}</strong>) — that's the signature of a sun-bias
        swap. One station catches morning sun, the other catches afternoon sun;
        their biases roughly cancel. Averaging them remains the right move —
        we get one warm-biased and one cool-biased reading at every afternoon
        hour, and the average is close to truth.
      `;
    }
    el.innerHTML = body;
  }

  async function load(range) {
    const meta = document.getElementById("stations-range-meta");
    if (meta) meta.textContent = "Loading…";

    let data;
    try {
      const r = await fetch(`/api/stations?range=${encodeURIComponent(range)}`, { cache: "no-store" });
      data = await r.json();
    } catch (err) {
      if (meta) meta.textContent = `Error: ${err.message}`;
      return;
    }

    const s550 = data.stations.KALHUNTS560.series || [];
    const s264 = data.stations.KALHUNTS264.series || [];
    const dser = data.paired_delta.series || [];
    const stats = data.paired_delta.stats || {};
    const cov550 = data.stations.KALHUNTS560.coverage || {};
    const cov264 = data.stations.KALHUNTS264.coverage || {};

    if (meta) {
      meta.textContent = `${s550.length} · ${s264.length} samples (${describeRange(range)})`;
    }

    bind("s560.temp", s550.length ? fmt(s550[s550.length - 1].temp_f) : "—");
    bind("s264.temp", s264.length ? fmt(s264[s264.length - 1].temp_f) : "—");
    bind("s560.coverage", cov550.n ? `${cov550.n.toLocaleString()} observations on file` : "no history yet");
    bind("s264.coverage", cov264.n ? `${cov264.n.toLocaleString()} observations on file` : "no history yet");
    bind("s560.range", cov550.first_ts ? `${cov550.first_ts.slice(0, 10)} → ${cov550.last_ts.slice(0, 10)}` : "—");
    bind("s264.range", cov264.first_ts ? `${cov264.first_ts.slice(0, 10)} → ${cov264.last_ts.slice(0, 10)}` : "—");

    bind("delta.mean",    fmtSigned(stats.mean));
    bind("delta.absMean", stats.abs_mean === null ? "—" : `${stats.abs_mean.toFixed(2)}°F`);
    bind("delta.stdev",   stats.stdev    === null ? "—" : stats.stdev.toFixed(2));
    bind("delta.n",       (stats.n || 0).toLocaleString());

    writeVerdict(stats, s550.length, s264.length, stats.n || 0);

    // ---- both stations chart ----
    if (stChart) stChart.destroy();
    stChart = new Chart(document.getElementById("stationsChart"), {
      type: "line",
      data: {
        datasets: [
          { label: "KALHUNTS560", data: s550.map((p) => ({ x: p.ts, y: p.temp_f })),
            borderColor: COL_560, borderWidth: 1.8, pointRadius: 0, tension: 0.2 },
          { label: "KALHUNTS264", data: s264.map((p) => ({ x: p.ts, y: p.temp_f })),
            borderColor: COL_264, borderWidth: 1.8, pointRadius: 0, tension: 0.2 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false, axis: "x" },
        plugins: {
          legend: { position: "top", align: "end", labels: { boxWidth: 14, boxHeight: 2, padding: 14 } },
          tooltip: {
            backgroundColor: "rgba(2,9,13,.92)", borderColor: "rgba(212,183,94,.25)", borderWidth: 1,
            callbacks: { title: fmtTooltipTitle,
                         label: (c) => `  ${c.dataset.label}: ${c.parsed.y.toFixed(2)}°F` },
          },
        },
        scales: {
          x: { type: "time", time: { unit: tickUnit(range) },
               grid: { color: "rgba(187,229,240,.06)" },
               ticks: { color: "rgba(241,234,212,.55)" } },
          y: { title: { display: true, text: "°F" },
               grid: { color: "rgba(187,229,240,.06)" },
               ticks: { color: "rgba(241,234,212,.55)" } },
        },
      },
    });

    // ---- delta chart ----
    if (dChart) dChart.destroy();
    dChart = new Chart(document.getElementById("deltaChart"), {
      type: "line",
      data: {
        datasets: [
          { label: "KALHUNTS560 − KALHUNTS264",
            data: dser.map((p) => ({ x: p.ts, y: p.delta })),
            borderColor: COL_GOLD, backgroundColor: "rgba(212,183,94,.10)",
            borderWidth: 1.6, pointRadius: 0, tension: 0.25, fill: true },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false, axis: "x" },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(2,9,13,.92)", borderColor: "rgba(212,183,94,.25)", borderWidth: 1,
            callbacks: { title: fmtTooltipTitle,
                         label: (c) => `  delta: ${c.parsed.y >= 0 ? "+" : "−"}${Math.abs(c.parsed.y).toFixed(2)}°F` },
          },
        },
        scales: {
          x: { type: "time", time: { unit: tickUnit(range) },
               grid: { color: "rgba(187,229,240,.06)" },
               ticks: { color: "rgba(241,234,212,.55)" } },
          y: { title: { display: true, text: "Δ °F" },
               grid: { color: "rgba(187,229,240,.06)" },
               ticks: { color: "rgba(241,234,212,.55)" } },
        },
      },
    });
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
})();

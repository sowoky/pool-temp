// /forecast — illuminated prophecy of pool water from NWS forecast.

(function () {
  if (typeof Chart === "undefined") return;

  Chart.defaults.color = "rgba(241, 234, 212, .72)";
  Chart.defaults.borderColor = "rgba(187, 229, 240, .12)";

  const css = getComputedStyle(document.documentElement);
  const COL_POOL  = (css.getPropertyValue("--pool") || "#38d6df").trim();
  const COL_AIR   = (css.getPropertyValue("--air")  || "#ff8a3d").trim();
  const COL_KHSV  = (css.getPropertyValue("--pws-264") || "#f5cb5c").trim();
  const COL_GOLD  = (css.getPropertyValue("--rune-gold") || "#d4b75e").trim();

  function fmt(v, digits = 1, unit = "°F") {
    return v === null || v === undefined || Number.isNaN(v)
      ? "—"
      : `${Number(v).toFixed(digits)}${unit}`;
  }
  function fmtSigned(v, digits = 1) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const s = Number(v) >= 0 ? "+" : "−";
    return `${s}${Math.abs(Number(v)).toFixed(digits)}°F`;
  }
  function bind(name, val) {
    document.querySelectorAll(`[data-bind="${name}"]`).forEach((el) => el.textContent = val);
  }

  async function load() {
    let data;
    try {
      const r = await fetch("/api/forecast", { cache: "no-store" });
      data = await r.json();
    } catch (err) {
      bind("prophecy.poolSub", `error: ${err.message}`);
      bind("prophecy.airSub",  `error: ${err.message}`);
      return;
    }

    const periods = data.periods || [];

    // "tomorrow" = the first period whose start is >= start-of-tomorrow,
    // falling back to the second-from-now period if midnight is too close.
    const now = new Date();
    const startOfTomorrow = new Date(now);
    startOfTomorrow.setHours(24, 0, 0, 0);
    let tmrIdx = periods.findIndex((p) => new Date(p.start) >= startOfTomorrow);
    if (tmrIdx < 0) tmrIdx = Math.min(periods.length - 1, 1);
    const tmr = periods[tmrIdx] || null;

    if (tmr) {
      bind("prophecy.poolTomorrow", fmt(tmr.pool_f));
      bind("prophecy.airTomorrow",  fmt(tmr.ms_air_f));
      bind("prophecy.poolSub",      `${tmr.name} · KHSV calls ${fmt(tmr.khsv_f, 0)}`);
      bind("prophecy.airSub",       `${tmr.name} · ${tmr.short_forecast || ""}`);
    } else {
      bind("prophecy.poolSub", "no NWS forecast available");
      bind("prophecy.airSub",  "no NWS forecast available");
    }

    bind("method.offset",   fmtSigned(data.ms_offset.value_f, 2));
    bind("method.offsetSrc", data.ms_offset.source);
    bind("method.offsetN",  data.ms_offset.samples.toLocaleString());
    bind("method.k",        `k = ${(data.pool_k.value).toFixed(3)}`);
    bind("method.kSrc",     data.pool_k.source);
    bind("method.kN",       data.pool_k.samples.toLocaleString());

    drawChart(periods);
    drawTable(periods);
  }

  function drawChart(periods) {
    const ctx = document.getElementById("prophecyChart");
    if (!ctx) return;
    const labels = periods.map((p) => p.name);
    const khsv   = periods.map((p) => p.khsv_f);
    const ms     = periods.map((p) => p.ms_air_f);
    const pool   = periods.map((p) => p.pool_f);

    if (window._prophecyChart) window._prophecyChart.destroy();
    window._prophecyChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "KHSV (valley)", data: khsv,
            borderColor: COL_KHSV, backgroundColor: "transparent",
            borderWidth: 1.6, borderDash: [4, 4], pointRadius: 3, tension: 0.25 },
          { label: "Monte Sano air (corrected)", data: ms,
            borderColor: COL_AIR, backgroundColor: "rgba(255,138,61,.08)",
            borderWidth: 2.2, pointRadius: 3, tension: 0.25, fill: false },
          { label: "Pool (modeled)", data: pool,
            borderColor: COL_POOL, backgroundColor: "rgba(56,214,223,.12)",
            borderWidth: 2.4, pointRadius: 4, tension: 0.25, fill: true,
            pointBackgroundColor: COL_GOLD, pointBorderColor: COL_GOLD },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false, axis: "x" },
        plugins: {
          legend: { position: "top", align: "end",
                    labels: { boxWidth: 14, boxHeight: 2, padding: 14 } },
          tooltip: {
            backgroundColor: "rgba(2,9,13,.92)", borderColor: "rgba(212,183,94,.25)",
            borderWidth: 1,
            callbacks: {
              label: (c) => `  ${c.dataset.label}: ${c.parsed.y === null ? "—" : c.parsed.y.toFixed(1) + "°F"}`,
            },
          },
        },
        scales: {
          x: { grid: { color: "rgba(187,229,240,.06)" },
               ticks: { color: "rgba(241,234,212,.55)", maxRotation: 45, minRotation: 0 } },
          y: { title: { display: true, text: "°F" },
               grid: { color: "rgba(187,229,240,.06)" },
               ticks: { color: "rgba(241,234,212,.55)" } },
        },
      },
    });
  }

  function drawTable(periods) {
    const host = document.getElementById("periodsTable");
    if (!host) return;
    const rows = periods.map((p) => `
      <tr>
        <td style="padding:.5rem .7rem; color: var(--bone);">${p.name || ""}</td>
        <td style="padding:.5rem .7rem; color: var(--pws-264); text-align:right;">${fmt(p.khsv_f, 0)}</td>
        <td style="padding:.5rem .7rem; color: var(--air); text-align:right;">${fmt(p.ms_air_f, 1)}</td>
        <td style="padding:.5rem .7rem; color: var(--pool); text-align:right;">${fmt(p.pool_f, 1)}</td>
        <td style="padding:.5rem .7rem; color: var(--bone-dim);">${p.short_forecast || ""}</td>
      </tr>`).join("");
    host.innerHTML = `
      <table style="width:100%; border-collapse: collapse; font-size: .85rem;
                    border:1px solid var(--hairline-2); border-radius: 12px; overflow:hidden;">
        <thead style="background: rgba(255,255,255,.03); color: var(--bone-faint);
                      text-transform: uppercase; letter-spacing: .15em; font-size: .68rem;">
          <tr>
            <th style="padding:.6rem .7rem; text-align:left;">Period</th>
            <th style="padding:.6rem .7rem; text-align:right;">KHSV</th>
            <th style="padding:.6rem .7rem; text-align:right;">MS air</th>
            <th style="padding:.6rem .7rem; text-align:right;">Pool</th>
            <th style="padding:.6rem .7rem; text-align:left;">Sky</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  load();
  setInterval(load, 10 * 60 * 1000);
})();

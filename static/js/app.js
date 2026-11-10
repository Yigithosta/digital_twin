import { api } from "./api.js";
import { createTwin } from "./twin.js";

// ── Durum ────────────────────────────────────────────────────────────────────
const S = {
  catalog: [],
  byId: {},
  latest: {},        // equipment_id → son okuma
  history: {},       // equipment_id → son okumalar (eskiden yeniye)
  alarms: [],
  summary: null,
  rul: {},           // equipment_id → RUL tahmini
  view: "genel",
  liveMode: null,
  lastReading: 0,
  trend: { eq: null, minutes: 60 },
  alarmFilter: { status: "open", eq: "" },
};
const HISTORY_MAX = 720;

const METRICS = [
  { key: "temperature", label: "Sıcaklık", digits: 1 },
  { key: "vibration", label: "Titreşim", digits: 2 },
  { key: "pressure", label: "Basınç", digits: 2 },
  { key: "current", label: "Akım", digits: 1 },
  { key: "gas", label: "Metan", digits: 2 },
  { key: "anomaly_score", label: "Anomali skoru", digits: 2 },
];
const VIEWS = {
  genel: ["Genel Bakış", "Filonun anlık durumu"],
  ikiz: ["Dijital İkiz", "Maden sahası › ekipman › sensör"],
  trend: ["Trendler", "Sensör geçmişi ve eşikler"],
  bakim: ["Kestirimci Bakım", "Kalan faydalı ömür ve kısa vadeli tahmin"],
  alarmlar: ["Alarmlar", "Anomali ve İSG kayıtları"],
  asistan: ["Teknik Asistan", "Servis dokümantasyonunda anlamsal arama"],
};

// ── Yardımcılar ──────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? "—" : Number(v).toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d }));
const int = (v) => (v == null ? "—" : Number(v).toLocaleString("tr-TR"));
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const timeOf = (iso) => new Date(iso).toLocaleTimeString("tr-TR");
const dateTime = (iso) => new Date(iso).toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const icon = (name) => `<svg class="ico" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const eqName = (id) => S.byId[id]?.name || id;
const worst = (levels) => (levels.includes("crit") ? "crit" : levels.includes("warn") ? "warn" : "ok");

function relTime(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
  if (s < 60) return "az önce";
  if (s < 3600) return `${Math.floor(s / 60)} dk önce`;
  if (s < 86400) return `${Math.floor(s / 3600)} sa önce`;
  return `${Math.floor(s / 86400)} gün önce`;
}

function toast(title, text = "", kind = "") {
  const box = $("toasts");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<div><strong>${esc(title)}</strong><span>${esc(text)}</span></div>`;
  box.append(el);
  while (box.children.length > 3) box.firstChild.remove();
  setTimeout(() => el.remove(), 6000);
}

// ── Durum değerlendirme ──────────────────────────────────────────────────────
function metricState(eq, key, v) {
  const lim = eq.limits[key];
  if (!lim || v == null) return "ok";
  if (lim.crit != null && v >= lim.crit) return "crit";
  if (lim.crit_low != null && v <= lim.crit_low) return "crit";
  if (lim.warn != null && (key === "gas" ? v >= lim.warn : v > lim.warn)) return "warn";
  if (lim.warn_low != null && v < lim.warn_low) return "warn";
  return "ok";
}

function eqState(id) {
  const eq = S.byId[id], d = S.latest[id];
  if (!d) return { level: "off", label: "Veri yok" };
  const levels = ["temperature", "vibration", "pressure", "current"].map((k) => metricState(eq, k, d[k]));
  const gas = metricState(eq, "gas", d.gas);
  if (gas === "crit") return { level: "crit", label: "Metan alarmı" };
  if (d.is_anomaly) return { level: "crit", label: "Anomali" };
  if (levels.includes("crit")) return { level: "crit", label: "Kritik" };
  if (gas === "warn") return { level: "warn", label: "Metan uyarısı" };
  if (levels.includes("warn")) return { level: "warn", label: "Uyarı" };
  return { level: "ok", label: "Normal" };
}

const isGasAlarm = (a) => (a.description || "").startsWith("İSG METAN");

// ── Grafikler ────────────────────────────────────────────────────────────────
const charts = new Set();

function chartTheme() {
  return { grid: css("--grid"), text: css("--muted"), accent: css("--series"), warn: css("--warn"), crit: css("--crit"), surface: css("--surface"), mono: css("--mono") };
}

function lineChart(canvas) {
  if (!window.Chart) {
    canvas.parentElement.innerHTML = `<div class="empty">Grafik kütüphanesi yüklenemedi.</div>`;
    return null;
  }
  const t = chartTheme();
  const chart = new window.Chart(canvas, {
    type: "line",
    data: { labels: [], datasets: [] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (item) => !item.dataset.threshold, displayColors: false,
          backgroundColor: t.surface, borderColor: t.grid, borderWidth: 1, cornerRadius: 6, padding: 8,
          titleColor: t.text, bodyColor: t.accent, titleFont: { family: t.mono, size: 10.5, weight: "400" }, bodyFont: { family: t.mono, size: 12 },
        },
      },
      scales: {
        x: { grid: { display: false }, border: { color: t.grid }, ticks: { color: t.text, maxTicksLimit: 6, maxRotation: 0, font: { size: 11, family: t.mono } } },
        y: { grid: { color: t.grid }, border: { display: false }, ticks: { color: t.text, maxTicksLimit: 5, font: { size: 11, family: t.mono } } },
      },
    },
  });
  charts.add(chart);
  return chart;
}

/** series: {labels, values, anomalies}, opts: {warn, crit, forecast, unit, yMin, yMax} */
function setSeries(chart, series, opts = {}) {
  if (!chart) return;
  const t = chartTheme();
  const n = series.values.length;
  const fc = opts.forecast || [];
  const labels = series.labels.map(timeOf).concat(fc.map((_, i) => `+${i + 1}`));
  const pad = (arr, len, fill = null) => arr.concat(Array(len).fill(fill));
  const anomalies = series.anomalies || [];

  const datasets = [{
    label: opts.label || "",
    data: pad(series.values, fc.length),
    borderColor: t.accent, backgroundColor: t.accent + "0f",
    borderWidth: 1.4, tension: 0.25, fill: true, spanGaps: true,
    pointRadius: anomalies.map((a) => (a ? 3.5 : 0)).concat(Array(fc.length).fill(0)),
    pointBackgroundColor: t.crit, pointBorderColor: t.crit, pointHoverRadius: 3,
  }];
  if (fc.length) {
    datasets.push({
      label: "Tahmin", data: Array(Math.max(0, n - 1)).fill(null).concat(n ? [series.values[n - 1]] : [], fc),
      borderColor: t.accent, borderWidth: 1.4, borderDash: [5, 4], tension: 0.25, pointRadius: 0, fill: false,
    });
  }
  const max = Math.max(...series.values.filter((v) => v != null), ...fc, -Infinity);
  const line = (value, color) => ({
    data: Array(labels.length).fill(value), borderColor: color, borderWidth: 1.2, borderDash: [4, 4],
    pointRadius: 0, fill: false, threshold: true,
  });
  if (opts.warn != null) datasets.push(line(opts.warn, t.warn));
  if (opts.crit != null && max >= opts.warn * 0.95) datasets.push(line(opts.crit, t.crit));

  chart.data.labels = labels;
  chart.data.datasets = datasets;
  chart.options.scales.y.min = opts.yMin;
  chart.options.scales.y.max = opts.yMax;
  chart.options.plugins.tooltip.callbacks = {
    label: (c) => `${c.dataset.label ? c.dataset.label + ": " : ""}${fmt(c.parsed.y, 2)}${opts.unit ? " " + opts.unit : ""}`,
  };
  chart.update();
}

function chartOpts(eq, key) {
  const lim = eq.limits[key] || {};
  const m = METRICS.find((x) => x.key === key);
  if (key === "anomaly_score") return { label: m.label, warn: 0.5, yMin: 0, yMax: 1 };
  return { label: m.label, unit: eq.units[key], warn: lim.warn, crit: lim.crit };
}

function localSeries(id, key, count) {
  const rows = (S.history[id] || []).slice(-count);
  return { labels: rows.map((r) => r.time), values: rows.map((r) => r[key]), anomalies: rows.map((r) => r.is_anomaly) };
}

// ── Genel Bakış ──────────────────────────────────────────────────────────────
function renderKpis() {
  const s = S.summary || {};
  const states = S.catalog.map((eq) => eqState(eq.id).level);
  const okCount = states.filter((l) => l === "ok").length;
  const items = [
    { label: "Normal çalışan ekipman", value: `${okCount}<small>/ ${S.catalog.length}</small>`, cls: worst(states) },
    { label: "Açık alarm", value: int(s.acik_alarm), cls: s.acik_alarm ? "crit" : "" },
    { label: "Son 24 saatte alarm", value: int(s.anomali_24h) },
    { label: "Normal çalışma oranı", value: s.normal_oran == null ? "—" : `${fmt(s.normal_oran, 1)}<small>%</small>` },
  ];
  $("kpis").innerHTML = items.map((k) => `
    <div class="kpi ${k.cls || ""}">
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value">${k.value}</div>
    </div>`).join("");
}

function reading(eq, d, m) {
  const st = metricState(eq, m.key, d[m.key]);
  return `<div class="reading ${st}"><dt>${m.label}</dt><dd>${fmt(d[m.key], m.digits)}<small>${esc(eq.units[m.key])}</small></dd></div>`;
}

function renderCard(eq) {
  const d = S.latest[eq.id];
  const st = eqState(eq.id);
  const el = $(`card-${eq.id}`);
  if (!el) return;
  el.className = `card ${st.level}`;
  const head = `<div class="card-head"><div><h3>${esc(eq.name)}</h3><p>${esc(eq.zone)}</p></div><span class="pill ${st.level}">${st.label}</span></div>`;
  if (!d) {
    el.innerHTML = `${head}<div class="empty">Bu ekipmandan henüz okuma gelmedi.</div>`;
    return;
  }
  const rul = S.rul[eq.id];
  const gasLvl = metricState(eq, "gas", d.gas);
  el.innerHTML = `
    ${head}
    <dl class="readings">${METRICS.slice(0, 4).map((m) => reading(eq, d, m)).join("")}</dl>
    <div class="card-foot">
      <span>Metan <b class="${gasLvl}">%${fmt(d.gas, 2)}</b>${rul?.rul_saat != null ? ` · Kalan ömür <b>≈ ${fmt(rul.rul_saat, 0)} sa</b>` : ""}</span>
      <a class="link" href="#/ikiz" data-focus="${esc(eq.id)}">İkizde aç ${icon("arrow")}</a>
    </div>`;
}

function renderBanner() {
  const rank = { UYARI: 1, TEHLİKE: 2, KRİTİK: 3 };
  let top = null;
  for (const eq of S.catalog) {
    const g = S.latest[eq.id]?.gas_status;
    if (g && rank[g.seviye] && (!top || rank[g.seviye] > rank[top.g.seviye])) top = { eq, g };
  }
  const el = $("isg-banner");
  el.hidden = !top;
  if (!top) return;
  el.classList.toggle("warn", top.g.seviye === "UYARI");
  $("isg-title").textContent = `İSG · Metan ${top.g.seviye.toLocaleLowerCase("tr")} — ${top.eq.name}`;
  $("isg-sub").textContent = top.g.mesaj;
}

function alarmFeedItem(a) {
  return `<li>
    <span class="dot ${a.resolved ? "" : isGasAlarm(a) ? "warn" : "crit"}"></span>
    <div class="feed-top"><span>${esc(eqName(a.equipment_id))}</span><time title="${esc(dateTime(a.time))}">${relTime(a.time)}</time></div>
    <div class="feed-desc">${esc(a.description || "—")}</div>
  </li>`;
}

function renderOverviewAlarms() {
  const list = S.alarms.slice(0, 5);
  $("ov-alarms").innerHTML = list.length ? list.map(alarmFeedItem).join("") : `<li class="empty">Kayıtlı alarm yok.</li>`;
}

let ovChart = null, ovSeries = null;
async function loadOverviewChart() {
  const id = $("ov-eq").value, key = $("ov-metric").value;
  try {
    ovSeries = await api.get(`/dashboard/timeseries/${id}/${key}?minutes=30&points=360`);
  } catch (e) {
    ovSeries = localSeries(id, key, 360);
  }
  drawOverviewChart();
}
function drawOverviewChart() {
  if (!ovSeries) return;
  ovChart ??= lineChart($("ov-chart"));
  setSeries(ovChart, ovSeries, chartOpts(S.byId[$("ov-eq").value], $("ov-metric").value));
}

// ── Dijital ikiz ─────────────────────────────────────────────────────────────
let twin = null;

function renderTwinSide(focusId = twin?.focused) {
  const side = $("twin-side");
  const fleet = `
    <div class="side-card">
      <div class="side-row"><h3>Ekipmanlar</h3><span class="muted">${S.catalog.length} adet</span></div>
      <div class="side-list">${S.catalog.map((eq) => {
        const st = eqState(eq.id), d = S.latest[eq.id];
        return `<button class="side-item ${eq.id === focusId ? "on" : ""}" data-focus="${esc(eq.id)}">
          <span class="dot ${st.level === "off" ? "" : st.level}"></span>
          <div><strong>${esc(eq.name)}</strong><span>${esc(eq.zone)}</span></div>
          <b class="${st.level}">${st.label}${d ? `<br><span>${fmt(d.temperature, 1)} °C</span>` : ""}</b>
        </button>`;
      }).join("")}</div>
    </div>`;
  if (!focusId) { side.innerHTML = fleet; return; }

  const eq = S.byId[focusId], d = S.latest[focusId], st = eqState(focusId), rul = S.rul[focusId];
  const row = (label, keys) => {
    const lvl = worst(keys.map((k) => metricState(eq, k, d?.[k])));
    const vals = keys.map((k) => `${fmt(d?.[k], METRICS.find((m) => m.key === k)?.digits ?? (d?.[k] < 10 ? 2 : 0))} ${esc(eq.units[k])}`).join(" · ");
    return `<div class="side-item" style="cursor:default"><span class="dot ${lvl}"></span><div><strong>${label}</strong><span>${vals}</span></div><b class="${lvl}">${{ ok: "Normal", warn: "Uyarı", crit: "Kritik" }[lvl]}</b></div>`;
  };
  side.innerHTML = `
    <div class="side-card">
      <div class="side-row"><h3>${esc(eq.name)}</h3><span class="pill ${st.level}">${st.label}</span></div>
      <p class="muted">${esc(eq.zone)} · ${esc(eq.id)}${d ? ` · ${timeOf(d.time)}` : ""}</p>
      ${rul?.rul_saat != null ? `
        <div class="meter">
          <div class="meter-head"><span>Sağlık (LSTM RUL)</span><b>%${fmt(rul.saglik_yuzde, 0)} · ≈ ${fmt(rul.rul_saat, 0)} sa</b></div>
          <div class="bar"><i class="${{ kirmizi: "crit", sari: "warn" }[rul.renk] || ""}" style="width:${clamp(rul.saglik_yuzde, 0, 100)}%"></i></div>
        </div>` : ""}
      <div class="side-list">
        ${row("Motor", ["temperature", "current"])}
        ${row("Basınç hattı", ["pressure"])}
        ${row("Mekanik / tahrik", ["vibration", "speed"])}
        ${row("Ortam gazı", ["gas"])}
      </div>
      <div class="side-actions">
        <button class="btn btn-sm" data-scenario="anomaly" data-eq="${esc(focusId)}">${icon("alert")}Arıza enjekte et</button>
        <button class="btn btn-sm" data-scenario="gas" data-eq="${esc(focusId)}">${icon("wind")}Metan kaçağı</button>
      </div>
      <a class="link" href="#/trend" data-trend="${esc(focusId)}">Trendleri aç ${icon("arrow")}</a>
    </div>
    ${fleet}`;
}

// ── Trendler ─────────────────────────────────────────────────────────────────
const trendCharts = {};
function buildTrendGrid() {
  $("trend-eq").innerHTML = S.catalog.map((eq) => `<button data-eq="${esc(eq.id)}">${esc(eq.name)}</button>`).join("");
  $("trend-grid").innerHTML = METRICS.map((m) => `
    <div class="mini">
      <div class="mini-head"><h3>${m.label}</h3><b id="tv-${m.key}">—</b></div>
      <div class="chart"><canvas id="tc-${m.key}"></canvas></div>
    </div>`).join("");
}
async function loadTrends() {
  const { eq: id, minutes } = S.trend;
  const eq = S.byId[id];
  document.querySelectorAll("#trend-eq button").forEach((b) => b.classList.toggle("on", b.dataset.eq === id));
  document.querySelectorAll("#trend-range button").forEach((b) => b.classList.toggle("on", +b.dataset.min === minutes));
  await Promise.all(METRICS.map(async (m) => {
    let series;
    try { series = await api.get(`/dashboard/timeseries/${id}/${m.key}?minutes=${minutes}&points=240`); }
    catch (e) { series = localSeries(id, m.key, 240); }
    if (S.trend.eq !== id) return;
    trendCharts[m.key] ??= lineChart($(`tc-${m.key}`));
    setSeries(trendCharts[m.key], series, chartOpts(eq, m.key));
    const last = S.latest[id]?.[m.key];
    $(`tv-${m.key}`).innerHTML = `${fmt(last, m.digits)}<small>${m.key === "anomaly_score" ? "" : esc(eq.units[m.key])}</small>`;
  }));
}

// ── Kestirimci bakım ─────────────────────────────────────────────────────────
function gauge(pct, level) {
  const r = 44, c = 2 * Math.PI * r;
  return `<div class="gauge ${level}">
    <svg viewBox="0 0 104 104"><circle class="g-track" cx="52" cy="52" r="${r}"/><circle class="g-fill" cx="52" cy="52" r="${r}" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - clamp(pct, 0, 100) / 100)}"/></svg>
    <div class="gauge-label"><b>%${fmt(pct, 0)}</b><span>Sağlık</span></div>
  </div>`;
}
const rulLevel = (r) => ({ kirmizi: "crit", sari: "warn" }[r?.renk] || "ok");

function renderRulCards() {
  $("rul-cards").innerHTML = S.catalog.map((eq) => {
    const r = S.rul[eq.id];
    if (!r || r.rul_saat == null) {
      return `<div class="card"><div class="card-head"><div><h3>${esc(eq.name)}</h3><p>${esc(eq.zone)}</p></div></div>
        <div class="empty">${esc(r?.error || "Tahmin hesaplanıyor…")}</div></div>`;
    }
    const lvl = rulLevel(r);
    const life = r.rul_saat >= 48 ? `${fmt(r.rul_gun, 1)}<small>gün</small>` : `${fmt(r.rul_saat, 1)}<small>saat</small>`;
    return `<div class="card ${lvl}">
      <div class="card-head"><div><h3>${esc(eq.name)}</h3><p>${esc(eq.zone)}</p></div><span class="pill ${lvl}">${esc(r.durum)}</span></div>
      <div class="rul">${gauge(r.saglik_yuzde, lvl)}<div><div class="muted">Tahmini kalan ömür</div><div class="rul-big">${r.rul_saat >= 99 ? "≥ " : ""}${life}</div></div></div>
      <div class="meter">
        <div class="meter-head"><span>Baskın belirti: ${esc(r.baskin_sensor)}</span><b>%${fmt(r.sensor_doluluk, 0)}</b></div>
        <div class="bar"><i class="${lvl}" style="width:${clamp(r.sensor_doluluk, 0, 100)}%"></i></div>
      </div>
      <div class="note">${esc(r.oneri)}</div>
    </div>`;
  }).join("");
}

async function loadRul() {
  await Promise.all(S.catalog.map(async (eq) => {
    try { S.rul[eq.id] = await api.get(`/predict/rul/${eq.id}`); }
    catch (e) { S.rul[eq.id] = { error: e.message }; }
  }));
  if (S.view === "bakim") renderRulCards();
  if (S.view === "genel") S.catalog.forEach(renderCard);
  if (S.view === "ikiz") renderTwinSide();
}

const fcCharts = {};
async function loadForecast() {
  const id = $("fc-eq").value, eq = S.byId[id];
  const keys = METRICS.slice(0, 4);
  if (!$("fc-grid").children.length) {
    $("fc-grid").innerHTML = keys.map((m) => `
      <div class="mini"><div class="mini-head"><h3>${m.label}</h3><b id="fv-${m.key}">—</b></div><div class="chart"><canvas id="fc-${m.key}"></canvas></div></div>`).join("");
  }
  let forecast = [];
  try { forecast = (await api.get(`/predict/${id}?steps=8`)).tahmin; } catch (e) { /* yeterli veri yok */ }
  keys.forEach((m) => {
    fcCharts[m.key] ??= lineChart($(`fc-${m.key}`));
    const fc = forecast.map((f) => f[m.key]);
    setSeries(fcCharts[m.key], localSeries(id, m.key, 30), { label: m.label, unit: eq.units[m.key], forecast: fc });
    $(`fv-${m.key}`).innerHTML = fc.length ? `${fmt(fc.at(-1), m.digits)}<small>${esc(eq.units[m.key])} · +${fc.length} adım</small>` : `<small>tahmin için veri bekleniyor</small>`;
  });
}

async function runScenario() {
  const id = $("sc-eq").value, out = $("sc-result"), btn = $("sc-run");
  btn.disabled = true;
  try {
    const r = await api.get(`/predict/rul/${id}?senaryo=degradasyon`);
    const lvl = rulLevel(r);
    const modes = { rulman_asinmasi: "Rulman aşınması", asiri_isinma: "Aşırı ısınma", asiri_akim: "Aşırı akım", basinc_kaybi: "Basınç kaybı" };
    out.innerHTML = `
      <div class="side-row"><strong>${esc(eqName(id))} · ${esc(modes[r.ariza_modu] || r.ariza_modu)}</strong><span class="pill ${lvl}">${esc(r.durum)}</span></div>
      <div class="compare">
        <div><span>Model tahmini</span><b>${fmt(r.rul_saat, 1)}<small>sa</small></b></div>
        <div><span>Gerçek kalan ömür</span><b>${fmt(r.gercek_rul, 1)}<small>sa</small></b></div>
        <div><span>Fark</span><b>${fmt(Math.abs(r.rul_saat - r.gercek_rul), 1)}<small>sa</small></b></div>
      </div>
      <div class="note">${esc(r.oneri)}</div>`;
  } catch (e) {
    out.innerHTML = `<div class="note">Senaryo çalıştırılamadı: ${esc(e.message)}</div>`;
  }
  btn.disabled = false;
}

// ── Alarmlar ─────────────────────────────────────────────────────────────────
function renderAlarms() {
  const { status, eq } = S.alarmFilter;
  const rows = S.alarms.filter((a) => (status === "all" || (status === "open") === !a.resolved) && (!eq || a.equipment_id === eq));
  $("al-body").innerHTML = rows.length ? rows.map((a) => `
    <tr class="${a.resolved ? "done" : ""}">
      <td class="t">${esc(dateTime(a.time))}</td>
      <td><strong>${esc(eqName(a.equipment_id))}</strong></td>
      <td>${isGasAlarm(a) ? `<span class="pill gas">İSG · Metan</span>` : `<span class="pill crit">Anomali</span>`}</td>
      <td class="t">${fmt(a.anomaly_score, 2)}</td>
      <td>${esc(a.description || "—")}</td>
      <td>${a.resolved ? `<span class="pill off">Çözüldü</span>` : `<span class="pill warn">Açık</span>`}</td>
      <td class="act">
        <button class="btn btn-sm" data-advice="${a.id}">${icon("book")}Öneri</button>
        ${a.resolved ? "" : `<button class="btn btn-sm" data-resolve="${a.id}">${icon("check")}Çöz</button>`}
      </td>
    </tr>`).join("") : `<tr><td colspan="7" class="empty">Bu filtreye uyan kayıt yok.</td></tr>`;
}

function ragResult(r) {
  return `<article class="result">
    <div class="result-top"><span class="result-cat">${esc(r.category)}</span>
      <span class="result-score">uyum %${fmt(r.score * 100, 0)}<span class="bar"><i style="width:${clamp(r.score * 100, 0, 100)}%"></i></span></span></div>
    <h3>${esc(r.title)}</h3><p>${esc(r.content)}</p>
    ${r.part_numbers?.length ? `<div class="parts">${r.part_numbers.map((p) => `<span>P/N ${esc(p)}</span>`).join("")}</div>` : ""}
  </article>`;
}

async function openAdvice(id) {
  const a = S.alarms.find((x) => x.id === id);
  if (!a) return;
  $("drawer").hidden = false;
  $("drawer-content").innerHTML = `
    <div class="note"><strong>${esc(eqName(a.equipment_id))}</strong> · ${esc(dateTime(a.time))}<br>${esc(a.description || "")}</div>
    <div class="empty">Dokümantasyonda aranıyor…</div>`;
  try {
    const type = S.byId[a.equipment_id]?.type || "";
    const res = await api.get(`/rag/anomali-asistan?ekipman=${encodeURIComponent(type)}&aciklama=${encodeURIComponent(a.description || "anomali")}`);
    $("drawer-content").lastElementChild.outerHTML = res.sonuclar?.length
      ? res.sonuclar.map(ragResult).join("")
      : `<div class="empty">Bilgi tabanında ilgili bölüm bulunamadı.</div>`;
  } catch (e) {
    $("drawer-content").lastElementChild.outerHTML = `<div class="empty">Öneri alınamadı: ${esc(e.message)}</div>`;
  }
}

async function resolveAlarm(id) {
  try {
    await api.post(`/anomalies/${id}/resolve`);
    const a = S.alarms.find((x) => x.id === id);
    if (a) a.resolved = true;
    renderAlarms();
    loadSummary();
  } catch (e) { toast("Kayıt güncellenemedi", e.message, "crit"); }
}

// ── Teknik asistan ───────────────────────────────────────────────────────────
async function ask(question) {
  const q = question.trim();
  if (q.length < 2) return;
  $("rag-q").value = q;
  $("rag-results").innerHTML = `<div class="empty">Aranıyor…</div>`;
  try {
    const res = await api.post("/rag/sor", { soru: q, limit: 4 });
    $("rag-results").innerHTML = res.sonuclar?.length
      ? res.sonuclar.map(ragResult).join("")
      : `<div class="empty">İlgili bölüm bulunamadı. Soruyu farklı ifade etmeyi deneyin.</div>`;
  } catch (e) {
    $("rag-results").innerHTML = `<div class="empty">Arama yapılamadı: ${esc(e.message)}</div>`;
  }
}

// ── Veri yükleme ─────────────────────────────────────────────────────────────
async function loadSummary() {
  try { S.summary = await api.get("/dashboard/summary"); } catch (e) { return; }
  const n = S.summary.acik_alarm;
  $("nav-alarm-count").hidden = !n;
  $("nav-alarm-count").textContent = n > 99 ? "99+" : n;
  if (S.view === "genel") renderKpis();
}

async function loadAlarms() {
  try { S.alarms = await api.get("/dashboard/recent-anomalies?limit=200"); } catch (e) { return; }
  if (S.view === "genel") renderOverviewAlarms();
  if (S.view === "alarmlar") renderAlarms();
}

async function loadHealth() {
  const set = (id, ok, text) => { $(id).className = `dot ${ok ? "ok" : "crit"}`; $(`${id}-t`).textContent = text; };
  try {
    const h = await api.get("/health");
    const c = h.bilesenler || {};
    if (api.isDemo) {
      $("sys-api").className = $("sys-mqtt").className = $("sys-rag").className = "dot warn";
      $("sys-api-t").textContent = $("sys-mqtt-t").textContent = $("sys-rag-t").textContent = "demo";
    } else {
      set("sys-api", c.veritabani, c.veritabani ? "çalışıyor" : "veritabanı yok");
      set("sys-mqtt", c.mqtt, c.mqtt ? "bağlı" : "kapalı");
      set("sys-rag", c.qdrant, c.qdrant ? "hazır" : "kapalı");
    }
  } catch (e) {
    set("sys-api", false, "ulaşılamıyor");
  }
}

function tickLive() {
  const age = (Date.now() - S.lastReading) / 1000;
  const fresh = S.lastReading && age < 20;
  $("live-ind").querySelector(".dot").className = `dot ${fresh ? "ok" : S.lastReading ? "warn" : ""}`;
  $("live-text").textContent = !S.lastReading ? "Veri bekleniyor…" : fresh ? `Canlı · ${timeOf(S.lastReading)}` : `Son veri ${Math.round(age)} sn önce`;
  const mode = { sse: "anlık", poll: "yoklama", demo: "demo" }[S.liveMode] || "—";
  $("sys-live").className = `dot ${fresh ? (S.liveMode === "sse" ? "ok" : "warn") : "crit"}`;
  $("sys-live-t").textContent = mode;
}

function onReading(r) {
  if (!S.byId[r.equipment_id]) return;
  const prev = S.latest[r.equipment_id];
  if (prev && prev.time === r.time) return;
  S.latest[r.equipment_id] = r;
  const h = (S.history[r.equipment_id] ??= []);
  h.push(r);
  if (h.length > HISTORY_MAX) h.shift();
  S.lastReading = Date.now();

  if (S.view === "genel") {
    renderCard(S.byId[r.equipment_id]);
    renderKpis();
    if (ovSeries && $("ov-eq").value === r.equipment_id) {
      const key = $("ov-metric").value;
      ovSeries.labels.push(r.time); ovSeries.values.push(r[key]); ovSeries.anomalies.push(r.is_anomaly);
      if (ovSeries.values.length > 360) { ovSeries.labels.shift(); ovSeries.values.shift(); ovSeries.anomalies.shift(); }
      drawOverviewChart();
    }
  }
  if (S.view === "ikiz") { twin?.paint(); renderTwinSide(); }
  renderBanner();
}

function onAlarm(a) {
  S.alarms.unshift(a);
  if (S.alarms.length > 300) S.alarms.pop();
  toast(`${isGasAlarm(a) ? "İSG · Metan" : "Anomali"} — ${eqName(a.equipment_id)}`, a.description || "", "crit");
  if (S.view === "genel") renderOverviewAlarms();
  if (S.view === "alarmlar") renderAlarms();
  loadSummary();
}

async function trigger(kind, id) {
  const q = kind === "gas" ? "force_gas=true" : "force_anomaly=true";
  try {
    const r = await api.post(`/sensors/simulate/${id}?${q}`);
    toast(kind === "gas" ? "Metan kaçağı senaryosu" : "Arıza senaryosu", `${eqName(id)} için sıra dışı okuma üretildi.`, "ok");
    if (!api.isDemo && S.liveMode !== "sse") {
      onReading({ ...r, gas_status: S.latest[id]?.gas_status });
      loadAlarms(); loadSummary();
    }
  } catch (e) { toast("Senaryo çalıştırılamadı", e.message, "crit"); }
}

// ── Görünümler ───────────────────────────────────────────────────────────────
function refreshView(force = false) {
  switch (S.view) {
    case "genel":
      renderKpis(); S.catalog.forEach(renderCard); renderOverviewAlarms();
      if (force || !ovSeries) loadOverviewChart(); else drawOverviewChart();
      break;
    case "ikiz":
      twin ??= createTwin({
        catalog: S.catalog, getLatest: (id) => S.latest[id], getState: eqState,
        metricState, fmt, onFocus: (id) => renderTwinSide(id),
      });
      twin.paint(); renderTwinSide();
      if (S.pendingFocus) { twin.focus(S.pendingFocus); S.pendingFocus = null; }
      break;
    case "trend": loadTrends(); break;
    case "bakim": renderRulCards(); loadForecast(); break;
    case "alarmlar": renderAlarms(); break;
  }
}

function route() {
  // #/ikiz?odak=pump_01 → doğrudan bir ekipmana odaklanan bağlantı
  const [name, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  const focus = new URLSearchParams(query).get("odak");
  if (focus && S.byId[focus]) S.pendingFocus = focus;
  S.view = VIEWS[name] ? name : "genel";
  document.querySelectorAll(".view").forEach((v) => { v.hidden = v.id !== `view-${S.view}`; });
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("on", a.dataset.view === S.view));
  document.querySelectorAll(".nav a").forEach((a) => (a.dataset.view === S.view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  [$("page-title").textContent, $("page-sub").textContent] = VIEWS[S.view];
  document.title = S.view === "genel" ? "Maden Dijital İkiz" : `${VIEWS[S.view][0]} · Maden Dijital İkiz`;
  refreshView(true);
}

function bindEvents() {
  window.addEventListener("hashchange", route);

  const menu = $("scenario-menu"), pop = menu.querySelector(".menu-pop");
  $("scenario-btn").onclick = () => { pop.hidden = !pop.hidden; $("scenario-btn").setAttribute("aria-expanded", String(!pop.hidden)); };
  document.addEventListener("click", (e) => { if (!menu.contains(e.target)) pop.hidden = true; });

  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-scenario],[data-focus],[data-trend],[data-resolve],[data-advice],[data-close]");
    if (!t) return;
    if (t.dataset.scenario) { trigger(t.dataset.scenario, t.dataset.eq || $("scenario-eq").value); pop.hidden = true; }
    else if (t.dataset.focus) { if (S.view === "ikiz") twin?.focus(t.dataset.focus); else S.pendingFocus = t.dataset.focus; }
    else if (t.dataset.trend) S.trend.eq = t.dataset.trend;
    else if (t.dataset.resolve) resolveAlarm(+t.dataset.resolve);
    else if (t.dataset.advice) openAdvice(+t.dataset.advice);
    else if ("close" in t.dataset) $("drawer").hidden = true;
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { $("drawer").hidden = true; pop.hidden = true; } });

  $("ov-eq").onchange = $("ov-metric").onchange = loadOverviewChart;
  $("trend-eq").onclick = (e) => { const b = e.target.closest("button"); if (b) { S.trend.eq = b.dataset.eq; loadTrends(); } };
  $("trend-range").onclick = (e) => { const b = e.target.closest("button"); if (b) { S.trend.minutes = +b.dataset.min; loadTrends(); } };
  $("rul-refresh").onclick = loadRul;
  $("fc-eq").onchange = loadForecast;
  $("sc-run").onclick = runScenario;

  $("al-status").onclick = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    S.alarmFilter.status = b.dataset.f;
    document.querySelectorAll("#al-status button").forEach((x) => x.classList.toggle("on", x === b));
    renderAlarms();
  };
  $("al-eq").onchange = (e) => { S.alarmFilter.eq = e.target.value; renderAlarms(); };
  $("al-resolve-all").onclick = async () => {
    const open = S.alarms.filter((a) => !a.resolved).length;
    if (!open || !confirm("Tüm açık alarmlar çözüldü olarak işaretlensin mi?")) return;
    try {
      const res = await api.post("/anomalies/resolve-all");
      toast("Alarmlar kapatıldı", `${res.adet} kayıt çözüldü işaretlendi.`, "ok");
      await Promise.all([loadAlarms(), loadSummary()]);
    } catch (e) { toast("İşlem başarısız", e.message, "crit"); }
  };

  $("rag-form").onsubmit = (e) => { e.preventDefault(); ask($("rag-q").value); };
  $("rag-quick").onclick = (e) => { const b = e.target.closest("button"); if (b) ask(b.textContent); };
}

// ── Başlangıç ────────────────────────────────────────────────────────────────
async function start() {
  S.catalog = await api.init();
  S.byId = Object.fromEntries(S.catalog.map((eq) => [eq.id, eq]));
  S.trend.eq = S.catalog[0]?.id;
  $("demo-chip").hidden = !api.isDemo;
  if (api.isDemo) $("al-pdf").hidden = true;
  else $("al-pdf").href = api.url("/report/anomali-pdf");

  const options = S.catalog.map((eq) => `<option value="${esc(eq.id)}">${esc(eq.name)}</option>`).join("");
  ["scenario-eq", "ov-eq", "fc-eq", "sc-eq"].forEach((id) => { $(id).innerHTML = options; });
  $("al-eq").innerHTML = `<option value="">Tüm ekipmanlar</option>${options}`;
  $("ov-metric").innerHTML = METRICS.map((m) => `<option value="${m.key}">${m.label}</option>`).join("");
  $("eq-cards").innerHTML = S.catalog.map((eq) => `<div class="card" id="card-${esc(eq.id)}"></div>`).join("");
  buildTrendGrid();
  bindEvents();

  // Geçmiş: kıvılcım grafikleri ve tahmin için son okumalar
  await Promise.all(S.catalog.map(async (eq) => {
    try {
      const rows = await api.get(`/sensors/history/${eq.id}?hours=1`);
      S.history[eq.id] = rows.reverse().slice(-HISTORY_MAX);
    } catch (e) { S.history[eq.id] = []; }
  }));
  try {
    const all = await api.get("/dashboard/latest-all");
    Object.assign(S.latest, all);
    if (Object.keys(all).length) S.lastReading = Date.now();
  } catch (e) { /* canlı akış dolduracak */ }

  route();
  renderBanner();
  await Promise.all([loadSummary(), loadAlarms(), loadHealth(), loadRul()]);
  try {
    const st = await api.get("/rag/status");
    $("rag-meta").textContent = st.toplam_belge != null
      ? `Bilgi tabanı: ${int(st.toplam_belge)} bölüm · ${st.model}`
      : "Bilgi tabanı şu anda kullanılamıyor.";
  } catch (e) { /* asistan görünümünde hata gösterilir */ }

  api.live({ onReading, onAlarm, onState: (mode) => { S.liveMode = mode; tickLive(); } });
  setInterval(tickLive, 1000);
  setInterval(loadSummary, 15000);
  setInterval(loadHealth, 15000);
  setInterval(loadRul, 30000);
  setInterval(() => {
    if (S.liveMode !== "sse") loadAlarms();
    if (S.view === "trend") loadTrends();
    if (S.view === "bakim") loadForecast();
    if (S.view === "genel") renderOverviewAlarms();   // göreli zamanları tazele
  }, 15000);
}

start().catch((e) => {
  document.querySelector(".content").innerHTML = `<div class="empty">Panel başlatılamadı: ${esc(e.message)}</div>`;
});

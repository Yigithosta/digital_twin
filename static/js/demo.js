// Demo modu: sunucu yokken arayüzü besleyen tarayıcı içi örnek veri üreteci.
// Sunucudaki simülatörle aynı ekipman profillerini ve eşik mantığını kullanır;
// modellerin yerine basit kurallar geçer. Üretilen veriler gerçek değildir.

const FEATURES = ["temperature", "vibration", "pressure", "current", "speed"];
const CRIT = { temperature: 1.45, vibration: 2.8, current: 1.6, pressure: 1.7 };
const PROFILES = {
  conveyor_01: { type: "conveyor", name: "Konveyör Bandı", zone: "Nakliye Ana Galerisi", speed_unit: "m/s",
    temperature: [45, 65], vibration: [1.5, 4.5], pressure: [2, 4], current: [18, 28], speed: [1.2, 1.8], gas: [0.1, 0.6] },
  pump_01: { type: "pump", name: "Pompa Ünitesi", zone: "Üretim Ayağı (Kuzey)", speed_unit: "rpm",
    temperature: [35, 55], vibration: [0.5, 2.5], pressure: [5, 8], current: [22, 35], speed: [1450, 1490], gas: [0.1, 0.6] },
  crusher_01: { type: "crusher", name: "Kırıcı", zone: "Üretim Ayağı (Güney)", speed_unit: "rpm",
    temperature: [50, 75], vibration: [3, 6.5], pressure: [3, 6], current: [30, 45], speed: [280, 320], gas: [0.1, 0.7] },
};
const KB = [
  { category: "Motor Sistemi", title: "Motor sıcaklık limitleri", part_numbers: ["56037200"],
    content: "Normal çalışma sıcaklığı 70–90°C aralığındadır. 95°C üzerinde uyarı alarmı devreye girer. Yüksek sıcaklıkta soğutma sıvısı seviyesini, radyatör temizliğini ve termostatı kontrol edin.",
    keys: "motor sıcaklık ısınma aşırı soğutma" },
  { category: "Titreşim ve Mekanik", title: "Titreşim eşikleri ve rulman bakımı", part_numbers: ["56204783", "56045500"],
    content: "5–8 mm/s erken uyarı bölgesidir; rulman kontrolü önerilir. 8 mm/s üzeri kritik eşiktir ve makine durdurulmalıdır. Burçlar 500 saat aralıkla değiştirilir.",
    keys: "titreşim rulman eşik mekanik bakım" },
  { category: "Hidrolik", title: "Hidrolik basınç ve pompa arızaları", part_numbers: ["56033411"],
    content: "Basınç düşüşünde önce yağ seviyesini ve filtreyi kontrol edin, ardından pompa emiş hattında hava kaçağı arayın. Ani basınç yükselmesinde emniyet valfini test edin.",
    keys: "hidrolik basınç pompa düşük yüksek arıza" },
  { category: "Periyodik Bakım", title: "Bakım takvimi", part_numbers: [],
    content: "Günlük: görsel kontrol ve yağ seviyeleri. 125 saat: bağlantı noktalarının greslenmesi. 250 saat: burç muayenesi. 500 saat: yağ ve filtre değişimi.",
    keys: "bakım takvim periyodik saat yağ filtre" },
  { category: "Güvenlik (İSG)", title: "Metan (CH₄) güvenlik eşikleri", part_numbers: [],
    content: "%1.0 üzerinde uyarı verilir ve havalandırma kontrol edilir. %1.5 üzerinde elektrikli ekipman durdurulur. %2.0 üzerinde tüm personel tahliye edilir.",
    keys: "metan gaz güvenlik isg tahliye eşik" },
];

const randn = () => {
  let u = 0, v = 0;
  while (!u) u = Math.random();
  while (!v) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
};
const uniform = (a, b) => a + Math.random() * (b - a);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const round = (v, d = 3) => Number(v.toFixed(d));

function limits(p) {
  const out = {};
  for (const k of ["temperature", "vibration", "pressure", "current"]) {
    const [lo, hi] = p[k];
    out[k] = { lo, hi, warn: round(hi * 1.1, 2), crit: round(hi * CRIT[k], 2) };
  }
  out.pressure.warn_low = round(p.pressure[0] * 0.85, 2);
  out.pressure.crit_low = round(p.pressure[0] * 0.45, 2);
  out.speed = { lo: p.speed[0], hi: p.speed[1] };
  out.gas = { lo: 0, hi: 1, warn: 1, crit: 1.5, evacuate: 2 };
  return out;
}

function gasStatus(g) {
  const t = g.toFixed(2);
  if (g >= 2) return { seviye: "KRİTİK", renk: "kirmizi", mesaj: `TAHLİYE — Metan %${t} (patlama riski). Tüm personel tahliye edilmeli.` };
  if (g >= 1.5) return { seviye: "TEHLİKE", renk: "turuncu", mesaj: `Metan %${t} — Elektrikli ekipmanı durdurun, havalandırmayı artırın.` };
  if (g >= 1) return { seviye: "UYARI", renk: "sari", mesaj: `Metan %${t} — Eşik aşıldı, havalandırma kontrol edilmeli.` };
  return { seviye: "NORMAL", renk: "yesil", mesaj: `Metan %${t} — Güvenli aralık.` };
}

export function createDemo() {
  const PHI = 0.85, STEP = 5000;
  const ids = Object.keys(PROFILES);
  const z = Object.fromEntries(ids.map((id) => [id, FEATURES.map(randn)]));
  const gz = Object.fromEntries(ids.map((id) => [id, 0]));
  const history = Object.fromEntries(ids.map((id) => [id, []]));
  const alarms = [];
  const gasLevel = {}, leak = {};
  let alarmId = 0, total = 48210;
  const listeners = { reading: [], alarm: [] };

  function step(id, time, { anomaly = false, gas = false, notify = true } = {}) {
    const p = PROFILES[id];
    const r = { equipment_id: id };
    const scores = [];
    z[id] = z[id].map((v) => PHI * v + Math.sqrt(1 - PHI * PHI) * randn());
    FEATURES.forEach((k, i) => {
      const [lo, hi] = p[k];
      r[k] = clamp((lo + hi) / 2 + z[id][i] * (hi - lo) / 6, lo * 0.9, hi * 1.1);
    });
    if (anomaly || Math.random() < 0.015) {
      const f = ["temperature", "vibration", "current", "pressure"][Math.floor(Math.random() * 4)];
      r[f] *= { temperature: uniform(1.3, 1.6), vibration: uniform(2, 3.5), current: uniform(1.4, 1.8), pressure: uniform(1.5, 2) }[f];
    }
    FEATURES.forEach((k) => {
      const [lo, hi] = p[k];
      scores.push(Math.abs(r[k] - (lo + hi) / 2) / ((hi - lo) / 6));
      r[k] = round(r[k]);
    });
    gz[id] = PHI * gz[id] + Math.sqrt(1 - PHI * PHI) * randn();
    const [glo, ghi] = p.gas;
    const base = clamp((glo + ghi) / 2 + gz[id] * (ghi - glo) / 4, 0, ghi * 1.2);
    leak[id] = (leak[id] || 0) * 0.72;
    if (gas || Math.random() < 0.003) leak[id] = Math.max(leak[id], uniform(1.2, 2.6) - base);
    if (leak[id] < 0.02) leak[id] = 0;
    r.gas = round(base + leak[id]);

    const worst = Math.max(...scores);
    r.is_anomaly = worst > 3.6;
    r.anomaly_score = round(clamp(worst > 3.6 ? 0.5 + (worst - 3.6) / 8 : worst / 7.2, 0, 1));
    r.gas_status = gasStatus(r.gas);
    r.time = new Date(time).toISOString();
    history[id].push(r);
    if (history[id].length > 20000) history[id].shift();
    total += 1;

    const raise = (description, score) => {
      const a = { id: ++alarmId, time: r.time, equipment_id: id, anomaly_score: score, description, resolved: false };
      alarms.unshift(a);
      if (notify) listeners.alarm.forEach((fn) => fn(a));
    };
    if (r.is_anomaly) {
      const i = scores.indexOf(worst), k = FEATURES[i];
      const name = { temperature: "sıcaklık", vibration: "titreşim", pressure: "basınç", current: "akım", speed: "hız" }[k];
      raise(`Anomali: yüksek ${name} (${r[k]}; normal ${p[k][0]}–${p[k][1]}) — skor ${r.anomaly_score.toFixed(2)}`, r.anomaly_score);
    }
    const rank = { NORMAL: 0, UYARI: 1, TEHLİKE: 2, KRİTİK: 3 }[r.gas_status.seviye];
    const escalated = rank > (gasLevel[id] || 0);
    gasLevel[id] = rank;
    if (escalated) raise(`İSG METAN ${r.gas_status.seviye}: ${r.gas_status.mesaj}`, 1);
    return r;
  }

  // Başlangıç için bir saatlik geçmiş
  const now = Date.now();
  for (let t = now - 3600e3; t < now; t += STEP) {
    ids.forEach((id) => step(id, t, { notify: false }));
  }
  alarms.slice(6).forEach((a) => { a.resolved = true; });

  setInterval(() => {
    ids.forEach((id) => { const r = step(id, Date.now()); listeners.reading.forEach((fn) => fn(r)); });
  }, STEP);

  function rul(id, scenario) {
    if (scenario === "degradasyon") {
      const actual = round(uniform(4, 24), 1), pred = round(Math.max(0.5, actual + randn() * 3), 1);
      return { equipment_id: id, rul_saat: pred, rul_gun: round(pred / 24, 1), saglik_yuzde: round(Math.min(100, pred / 0.6), 1),
        durum: pred < 8 ? "KRİTİK" : "UYARI", renk: pred < 8 ? "kirmizi" : "sari", baskin_sensor: "Titreşim",
        sensor_doluluk: round(100 - actual * 3, 1), senaryo: "degradasyon", gercek_rul: actual, ariza_modu: "rulman_asinmasi",
        oneri: pred < 8 ? "Acil bakım planlayın. Titreşim kritik eşiğe çok yakın." : "24 saat içinde bakım planlanmalı. Titreşim trendi yükseliyor." };
    }
    const hours = round(uniform(92, 99.8), 1);
    return { equipment_id: id, rul_saat: hours, rul_gun: round(hours / 24, 1), saglik_yuzde: 100, durum: "SAĞLIKLI", renk: "yesil",
      baskin_sensor: "Titreşim", sensor_doluluk: 0, senaryo: "canlı", oneri: "Tüm parametreler normal. Planlı bakım takvimine uyun." };
  }

  function search(text, limit) {
    const words = text.toLocaleLowerCase("tr").split(/\s+/).filter((w) => w.length > 2);
    return KB.map((d) => {
      const hay = (d.keys + " " + d.title).toLocaleLowerCase("tr");
      const hit = words.filter((w) => hay.includes(w.slice(0, 5))).length;
      return { ...d, score: round(Math.min(0.95, 0.3 + 0.22 * hit), 3), hit };
    }).filter((d) => d.hit).sort((a, b) => b.score - a.score).slice(0, limit)
      .map(({ keys, hit, ...d }) => d);
  }

  const routes = [
    ["GET", /^\/equipment$/, () => ids.map((id) => {
      const p = PROFILES[id];
      return { id, type: p.type, name: p.name, zone: p.zone, limits: limits(p),
        units: { temperature: "°C", vibration: "mm/s", pressure: "bar", current: "A", speed: p.speed_unit, gas: "% CH₄" } };
    })],
    ["GET", /^\/health$/, () => ({ status: "ok", versiyon: "demo", bilesenler: { mqtt: false, veritabani: false, redis: false, qdrant: false } })],
    ["GET", /^\/dashboard\/summary$/, () => {
      const day = Date.now() - 864e5, hour = Date.now() - 36e5;
      const recent = ids.flatMap((id) => history[id]);
      const flagged = recent.filter((r) => r.is_anomaly).length;
      return { toplam_okuma: total, okuma_24h: recent.length, normal_oran: round(100 * (1 - flagged / recent.length), 2),
        anomali_24h: alarms.filter((a) => Date.parse(a.time) >= day).length,
        anomali_1h: alarms.filter((a) => Date.parse(a.time) >= hour).length,
        acik_alarm: alarms.filter((a) => !a.resolved).length };
    }],
    ["GET", /^\/dashboard\/latest-all$/, () => Object.fromEntries(ids.map((id) => [id, history[id].at(-1)]))],
    ["GET", /^\/dashboard\/recent-anomalies/, (m, q) => alarms.slice(0, Number(q.get("limit") || 8))],
    ["GET", /^\/dashboard\/timeseries\/(\w+)\/(\w+)/, (m, q) => {
      const since = Date.now() - Number(q.get("minutes") || 30) * 6e4;
      const rows = (history[m[1]] || []).filter((r) => Date.parse(r.time) >= since);
      const stepN = Math.max(1, Math.ceil(rows.length / Number(q.get("points") || 240)));
      const out = { labels: [], values: [], anomalies: [] };
      for (let i = 0; i < rows.length; i += stepN) {
        const chunk = rows.slice(i, i + stepN);
        out.labels.push(chunk.at(-1).time);
        out.values.push(round(chunk.reduce((s, r) => s + r[m[2]], 0) / chunk.length));
        out.anomalies.push(chunk.some((r) => r.is_anomaly));
      }
      return out;
    }],
    ["GET", /^\/sensors\/history\/(\w+)/, (m) => (history[m[1]] || []).slice(-500).reverse()],
    ["POST", /^\/sensors\/simulate\/(\w+)/, (m, q) => {
      const r = step(m[1], Date.now(), { anomaly: q.get("force_anomaly") === "true", gas: q.get("force_gas") === "true" });
      listeners.reading.forEach((fn) => fn(r));
      return r;
    }],
    ["POST", /^\/anomalies\/(\d+)\/resolve$/, (m) => {
      const a = alarms.find((x) => x.id === Number(m[1]));
      if (a) a.resolved = true;
      return { status: "çözüldü", id: Number(m[1]) };
    }],
    ["POST", /^\/anomalies\/resolve-all$/, () => {
      const n = alarms.filter((a) => !a.resolved).length;
      alarms.forEach((a) => { a.resolved = true; });
      return { status: "çözüldü", adet: n };
    }],
    ["GET", /^\/predict\/rul\/(\w+)/, (m, q) => rul(m[1], q.get("senaryo"))],
    ["GET", /^\/predict\/(\w+)/, (m, q) => {
      const p = PROFILES[m[1]], last = history[m[1]].at(-1);
      let cur = FEATURES.map((k) => last[k] - (p[k][0] + p[k][1]) / 2);
      const tahmin = [];
      for (let i = 0; i < Number(q.get("steps") || 6); i++) {
        cur = cur.map((d) => d * PHI);
        tahmin.push(Object.fromEntries(FEATURES.map((k, j) => [k, round((p[k][0] + p[k][1]) / 2 + cur[j])])));
      }
      return { equipment_id: m[1], adim_saniye: STEP / 1000, tahmin };
    }],
    ["GET", /^\/rag\/status$/, () => ({ durum: "demo", koleksiyon: "örnek", toplam_belge: KB.length, model: "anahtar kelime eşleşmesi" })],
    ["POST", /^\/rag\/sor$/, (m, q, body) => ({ soru: body.soru, sonuclar: search(body.soru, body.limit || 3), kaynak: "Örnek bilgi tabanı (demo)" })],
    ["GET", /^\/rag\/anomali-asistan/, (m, q) => {
      const sonuclar = search(q.get("aciklama") || "", 2);
      return { soru: q.get("aciklama"), sonuclar, ozet: sonuclar.length ? `İlgili ${sonuclar.length} bölüm bulundu.` : "Bilgi tabanında ilgili kayıt bulunamadı." };
    }],
  ];

  return {
    async request(method, path, body) {
      const [pathname, query = ""] = path.split("?");
      for (const [m, re, fn] of routes) {
        const match = m === method && pathname.match(re);
        if (match) return JSON.parse(JSON.stringify(fn(match, new URLSearchParams(query), body)));
      }
      throw new Error("Demo modunda desteklenmiyor: " + path);
    },
    subscribe(onReading, onAlarm) {
      listeners.reading.push(onReading);
      listeners.alarm.push(onAlarm);
    },
  };
}

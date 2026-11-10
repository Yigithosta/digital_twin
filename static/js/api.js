// API istemcisi. Sunucuya ulaşılamazsa (veya adreste ?demo varsa) tarayıcı içi
// örnek veri üretecine geçer; arayüzün geri kalanı farkı bilmez.

const params = new URLSearchParams(location.search);
const BASE = (params.get("api") || location.origin).replace(/\/$/, "");

let demo = null;

async function request(method, path, body) {
  if (demo) return demo.request(method, path, body);
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* gövde yok */ }
    const err = new Error(typeof detail === "string" ? detail : "İstek başarısız");
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  get isDemo() { return demo !== null; },
  url: (path) => BASE + path,

  /** Sunucuyu yoklar; ekipman kataloğunu döner. */
  async init() {
    if (!params.has("demo")) {
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 3500);
        const res = await fetch(BASE + "/equipment", { signal: ctrl.signal });
        clearTimeout(timer);
        if (res.ok) return res.json();
      } catch (e) { /* demo moduna düş */ }
    }
    demo = (await import("./demo.js")).createDemo();
    return demo.request("GET", "/equipment");
  },

  /** Canlı akış: onReading / onAlarm geri çağrıları, onState("sse" | "poll" | "demo"). */
  live({ onReading, onAlarm, onState }) {
    if (demo) {
      demo.subscribe(onReading, onAlarm);
      onState("demo");
      return;
    }
    let pollTimer = null;
    const poll = async () => {
      try {
        const all = await request("GET", "/dashboard/latest-all");
        Object.values(all).forEach(onReading);
      } catch (e) { /* bir sonraki turda yeniden denenir */ }
    };
    const startPolling = () => {
      if (pollTimer) return;
      onState("poll");
      poll();
      pollTimer = setInterval(poll, 5000);
    };
    if (!("EventSource" in window)) return startPolling();

    const es = new EventSource(BASE + "/stream");
    es.addEventListener("open", () => {
      clearInterval(pollTimer);
      pollTimer = null;
      onState("sse");
    });
    es.addEventListener("reading", (e) => onReading(JSON.parse(e.data)));
    es.addEventListener("alarm", (e) => onAlarm(JSON.parse(e.data)));
    es.addEventListener("error", startPolling);   // EventSource kendiliğinden yeniden bağlanır
  },
};

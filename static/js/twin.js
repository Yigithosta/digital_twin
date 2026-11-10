// Dijital ikiz sahnesi: yakınlaştıkça detaylanan (LOD) maden haritası.
//   makro  → saha geneli, ekipman noktaları
//   orta   → ekipman etiketleri ve anlık değerler
//   detay  → ekipman şeması, sensör konumları

const POS = { conveyor_01: [450, 470], pump_01: [700, 280], crusher_01: [950, 600] };
const FALLBACK_POS = [[560, 470], [820, 470], [1160, 320], [300, 380]];
const CX = 650, CY = 380;                 // viewBox merkezi
const LOD_MID = 1.6, LOD_DETAIL = 3.2;
const K_FOCUS = 8, K_SENSOR = 15;
const S = 0.14;                           // şemanın saha ölçeği (820×430 birimlik çizim)
const ORIGIN = [410, 230];

const spokes = (cx, cy, r) =>
  `<g class="spin"><path class="sc-thin" d="M${cx - r} ${cy}H${cx + r}M${cx} ${cy - r}V${cy + r}"/><circle cx="${cx}" cy="${cy}" r="${r}" fill="none"/></g>`;

function callout(key, label, [bx, by, bw], [dx, dy]) {
  const below = dy > by;                  // nokta kutunun altında mı
  const lx = Math.max(bx + 14, Math.min(bx + bw - 14, dx));
  return `
    <g class="co" data-co="${key}" data-x="${dx}" data-y="${dy}">
      <path class="co-line" d="M${dx} ${dy}L${lx} ${below ? by + 46 : by}"/>
      <circle class="co-dot" cx="${dx}" cy="${dy}" r="6"/>
      <rect class="co-box" x="${bx}" y="${by}" width="${bw}" height="46" rx="8"/>
      <text class="co-label" x="${bx + 12}" y="${by + 18}">${label}</text>
      <text class="co-value" x="${bx + 12}" y="${by + 38}">—</text>
      <rect class="co-hit" x="${bx}" y="${by}" width="${bw}" height="46" rx="8"><title>${label}</title></rect>
    </g>`;
}

const SCHEMATICS = {
  conveyor: () => `
    <ellipse class="sc-gas" cx="410" cy="150" rx="170" ry="34"/>
    <path class="sc-line" d="M130 372H700M230 330V372M350 330V372M470 330V372M590 330V372"/>
    <g class="sc-shake">
      <path class="sc-line sc-rot" stroke-width="7" d="M180 256L640 250A40 40 0 0 1 640 330L180 324A34 34 0 0 1 180 256Z"/>
      <path class="sc-ore" d="M300 248l14-16 18 6 12 10ZM380 247l16-20 20 8 14 12ZM470 246l12-14 16 4 10 10Z"/>
      ${[260, 340, 420, 500, 580].map((x) => `<circle class="sc-dark" cx="${x}" cy="270" r="8"/>`).join("")}
      <circle class="sc-dark" cx="180" cy="290" r="24"/>${spokes(180, 290, 17)}
      <circle class="sc-dark" cx="640" cy="290" r="30"/>${spokes(640, 290, 22)}
      <rect class="sc-body" x="84" y="279" width="62" height="22" rx="4"/><path class="sc-line" d="M146 290H158"/>
      <path class="sc-thin" d="M650 232L640 262M690 232L662 270"/>
      <rect class="sc-body sc-motor" x="610" y="176" width="124" height="56" rx="7"/>
      <path class="sc-thin" d="M634 186V222M654 186V222M674 186V222M694 186V222M714 186V222"/>
    </g>
    ${callout("gas", "ORTAM · METAN", [310, 40, 200], [410, 120])}
    ${callout("motor", "TAHRİK MOTORU", [560, 96, 220], [672, 204])}
    ${callout("pres", "GERGİ HİDROLİĞİ", [36, 180, 190], [115, 290])}
    ${callout("vib", "TAHRİK TAMBURU", [530, 372, 220], [640, 290])}`,

  pump: () => `
    <ellipse class="sc-gas" cx="660" cy="170" rx="130" ry="32"/>
    <path class="sc-line" d="M150 362H680"/>
    <g class="sc-shake">
      <rect class="sc-body" x="200" y="334" width="450" height="22" rx="4"/>
      <rect class="sc-body" x="170" y="256" width="72" height="40"/><rect class="sc-fill" x="158" y="246" width="12" height="60" rx="3"/>
      <path class="sc-body" d="M276 226V152H324V226Z"/><rect class="sc-fill" x="264" y="140" width="72" height="12" rx="3"/>
      <circle class="sc-body" cx="300" cy="276" r="64"/>
      <circle class="sc-dark" cx="300" cy="276" r="28"/>${spokes(300, 276, 20)}
      <path class="sc-line" d="M364 276H432"/>
      <circle class="sc-dark sc-rot" cx="398" cy="276" r="18"/>${spokes(398, 276, 12)}
      <rect class="sc-body sc-motor" x="432" y="222" width="190" height="108" rx="12"/>
      <path class="sc-thin" d="M462 236V316M488 236V316M514 236V316M540 236V316M566 236V316M592 236V316"/>
      <rect class="sc-fill" x="622" y="248" width="16" height="56" rx="4"/>
    </g>
    ${callout("pres", "ÇIKIŞ BASINCI", [205, 56, 190], [300, 150])}
    ${callout("gas", "ORTAM · METAN", [560, 70, 200], [660, 144])}
    ${callout("vib", "KAPLİN / YATAK", [150, 376, 210], [398, 276])}
    ${callout("motor", "ELEKTRİK MOTORU", [440, 376, 220], [527, 276])}`,

  crusher: () => `
    <ellipse class="sc-gas" cx="400" cy="112" rx="150" ry="30"/>
    <path class="sc-line" d="M120 372H790"/>
    <g class="sc-shake">
      <path class="sc-body" d="M250 150H520L560 362H230Z"/>
      <path class="sc-body" d="M270 150L240 100H530L500 150Z"/>
      <path class="sc-dark" d="M300 162H470L410 332H372Z"/>
      <path class="sc-ore" d="M330 190l20-22 24 8 16 16ZM396 196l18-18 22 10 8 14ZM372 250l14-16 16 8 6 12Z"/>
      <path class="sc-line" stroke-width="7" d="M306 168L374 326M464 168L408 326"/>
      <rect class="sc-body" x="150" y="292" width="76" height="22" rx="4"/><path class="sc-line" d="M226 303H240"/>
      <path class="sc-thin" d="M560 286L690 326M640 298L740 322"/>
      <circle class="sc-dark sc-rot" cx="600" cy="232" r="70"/>${spokes(600, 232, 56)}
      <circle class="sc-fill" cx="600" cy="232" r="13"/>
      <rect class="sc-body sc-motor" x="652" y="318" width="124" height="50" rx="7"/>
      <path class="sc-thin" d="M676 328V358M698 328V358M720 328V358M742 328V358"/>
    </g>
    ${callout("gas", "ORTAM · METAN", [300, 20, 200], [400, 84])}
    ${callout("vib", "VOLAN YATAĞI", [606, 80, 190], [600, 232])}
    ${callout("pres", "HİDROLİK AYAR", [26, 196, 190], [188, 303])}
    ${callout("motor", "TAHRİK MOTORU", [590, 384, 220], [714, 343])}`,
};

export function createTwin({ catalog, getLatest, getState, metricState, fmt, onFocus }) {
  const d3 = window.d3;
  const svgEl = document.getElementById("twin-map");
  if (!d3) {
    svgEl.insertAdjacentHTML("afterend", `<div class="empty">Harita kütüphanesi yüklenemedi (internet bağlantısını kontrol edin).</div>`);
    return { paint() {}, focus() {}, reset() {} };
  }

  const svg = d3.select(svgEl);
  const world = d3.select("#twin-world");
  const layer = d3.select("#twin-equipment");
  const pos = {};
  let focused = null;

  catalog.forEach((eq, i) => {
    const [x, y] = pos[eq.id] = POS[eq.id] || FALLBACK_POS[i % FALLBACK_POS.length];
    const g = layer.append("g").attr("class", "tw-eq").attr("data-eq", eq.id);
    g.html(`
      <g class="tw-macro">
        <circle class="halo" cx="${x}" cy="${y}" r="22"/>
        <circle class="core" cx="${x}" cy="${y}" r="9"/>
        <text class="name" x="${x}" y="${y - 30}" text-anchor="middle">${eq.name}</text>
      </g>
      <g class="tw-mid">
        <path class="co-line" d="M${x} ${y}V${y - 26}"/>
        <circle class="core" cx="${x}" cy="${y}" r="6"/>
        <rect class="tag" x="${x - 78}" y="${y - 70}" width="156" height="44" rx="8"/>
        <rect class="tag-bar" x="${x - 78}" y="${y - 70}" width="5" height="44" rx="2.5"/>
        <text class="name" x="${x - 64}" y="${y - 52}">${eq.name}</text>
        <text class="sub" x="${x - 64}" y="${y - 36}">—</text>
      </g>
      <g class="tw-detail" transform="translate(${x},${y}) scale(${S}) translate(${-ORIGIN[0]},${-ORIGIN[1]})">
        ${(SCHEMATICS[eq.type] || SCHEMATICS.pump)()}
      </g>`);
    g.select(".tw-macro").on("click", () => focus(eq.id));
    g.select(".tw-mid").on("click", () => focus(eq.id));
    g.selectAll(".co").on("click", function (event) {
      event.stopPropagation();
      zoomTo(x + (+this.dataset.x - ORIGIN[0]) * S, y + (+this.dataset.y - ORIGIN[1]) * S, K_SENSOR);
    });
  });

  const zoom = d3.zoom().scaleExtent([0.8, 20]).on("zoom", (e) => {
    world.attr("transform", e.transform);
    onZoom(e.transform);
  });
  svg.call(zoom).on("dblclick.zoom", null);

  function onZoom(t) {
    const lod = t.k >= LOD_DETAIL ? "detail" : t.k >= LOD_MID ? "mid" : "macro";
    svgEl.dataset.lod = lod;
    document.getElementById("twin-zoom").textContent = t.k.toFixed(1) + "×";

    let next = null;
    if (lod === "detail") {
      const [cx, cy] = t.invert([CX, CY]);
      let best = 200;
      for (const eq of catalog) {
        const d = Math.hypot(pos[eq.id][0] - cx, pos[eq.id][1] - cy);
        if (d < best) { best = d; next = eq.id; }
      }
    }
    if (next !== focused) {
      focused = next;
      const eq = catalog.find((e) => e.id === focused);
      document.getElementById("twin-crumb").textContent = eq ? `Maden sahası › ${eq.name}` : "Maden sahası";
      onFocus(focused);
    }
  }

  function zoomTo(wx, wy, k) {
    svg.transition().duration(650)
      .call(zoom.transform, d3.zoomIdentity.translate(CX - wx * k, CY - wy * k).scale(k));
  }
  function focus(id) { if (pos[id]) zoomTo(pos[id][0], pos[id][1], K_FOCUS); }
  function reset() { svg.transition().duration(650).call(zoom.transform, d3.zoomIdentity); }

  document.getElementById("twin-in").onclick = () => svg.transition().duration(200).call(zoom.scaleBy, 1.5);
  document.getElementById("twin-out").onclick = () => svg.transition().duration(200).call(zoom.scaleBy, 1 / 1.5);
  document.getElementById("twin-reset").onclick = reset;

  const worst = (...levels) => (levels.includes("crit") ? "crit" : levels.includes("warn") ? "warn" : "ok");

  function paint() {
    for (const eq of catalog) {
      const d = getLatest(eq.id);
      if (!d) continue;
      const g = layer.select(`[data-eq="${eq.id}"]`);
      const st = (k) => metricState(eq, k, d[k]);
      const level = getState(eq.id).level;
      g.attr("class", `tw-eq ${level === "off" ? "" : level}`);
      g.select(".tw-mid .sub").text(`${fmt(d.temperature, 1)} °C · ${fmt(d.vibration, 2)} mm/s`);

      const set = (key, text, lvl) => {
        const co = g.select(`[data-co="${key}"]`);
        co.attr("class", `co ${lvl}`).select(".co-value").text(text);
      };
      const motor = worst(st("temperature"), st("current"));
      set("motor", `${fmt(d.temperature, 1)} °C · ${fmt(d.current, 1)} A`, motor);
      set("pres", `${fmt(d.pressure, 2)} bar`, st("pressure"));
      set("vib", `${fmt(d.vibration, 2)} mm/s · ${fmt(d.speed, d.speed < 10 ? 2 : 0)} ${eq.units.speed}`, st("vibration"));
      set("gas", `%${fmt(d.gas, 2)} CH₄`, st("gas"));

      g.select(".sc-motor").attr("class", `sc-body sc-motor ${motor}`);
      g.selectAll(".sc-rot").classed("warn", st("vibration") === "warn").classed("crit", st("vibration") === "crit");
      g.select(".sc-shake").classed("shake", st("vibration") !== "ok");
      g.select(".sc-gas").classed("on", d.gas >= eq.limits.gas.warn);
    }
  }

  onZoom(d3.zoomIdentity);
  return { paint, focus, reset, get focused() { return focused; } };
}

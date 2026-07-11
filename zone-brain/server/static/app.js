/* CrowdVision dashboard client. Leaflet local-CRS floorplan + live WS feed.
   Renders zones (risk), gates, officers, feed-health chips, and the provenance
   decision log. Code to docs/MESSAGES.md. */
"use strict";

const RISK_COLOR = { GREEN: "#16a34a", AMBER: "#f59e0b", RED: "#dc2626", UNKNOWN: "#6b7280" };
const GATE_ICON = {
  OPEN: "🟢", SAFE_FLASH: "🟢", DIVERT_LEFT: "⬅️", DIVERT_RIGHT: "➡️",
  CLOSE: "🛑", CLOSE_DIVERT_LEFT: "🛑", CLOSE_DIVERT_RIGHT: "🛑",
};
const OVERRIDE_ACTIONS = ["OPEN", "DIVERT_LEFT", "CLOSE_DIVERT_LEFT", "SAFE_FLASH"];

let CFG = null, map = null;
const zoneLayers = {}, gateLayers = {}, gateState = {}, officerLayers = {};

const $ = (id) => document.getElementById(id);
const XY = (x, y) => L.latLng(y, x);   // CRS.Simple: lat=y, lng=x

function latlonToFloor(lat, lon) {
  const b = CFG.bounds, bb = CFG.officer_bbox;
  const [minx, miny] = b[0], [maxx, maxy] = b[1];
  const fx = minx + (lon - bb.lon[0]) / (bb.lon[1] - bb.lon[0]) * (maxx - minx);
  const fy = miny + (lat - bb.lat[0]) / (bb.lat[1] - bb.lat[0]) * (maxy - miny);
  return XY(Math.max(minx, Math.min(maxx, fx)), Math.max(miny, Math.min(maxy, fy)));
}

async function init() {
  CFG = await (await fetch("/api/config")).json();
  buildMap();
  buildGatePanel();
  buildCamPreviews();
  tickClock();
  connectWS();
}

function buildMap() {
  const b = CFG.bounds, sw = [b[0][1], b[0][0]], ne = [b[1][1], b[1][0]];
  map = L.map("map", { crs: L.CRS.Simple, minZoom: -4, zoomControl: true, attributionControl: false });
  // floor backdrop
  L.rectangle([sw, ne], { color: "#223040", weight: 1, fill: true, fillColor: "#0d141c", fillOpacity: 1 }).addTo(map);
  CFG.zones.forEach((z) => {
    const pts = z.polygon.map(([x, y]) => XY(x, y));
    const poly = L.polygon(pts, { color: "#334155", weight: 1.5, fillColor: RISK_COLOR.UNKNOWN, fillOpacity: 0.35 }).addTo(map);
    const cam = z.camera_id ? ` ← ${z.camera_id}` : " (no camera)";
    poly.bindTooltip(`Zone ${z.id}${cam}`, { permanent: true, direction: "center", className: "zone-label" });
    zoneLayers[z.id] = poly;
  });
  CFG.gates.forEach((g) => {
    const m = L.marker(XY(g.pos[0], g.pos[1]), {
      icon: L.divIcon({ className: "", html: `<div class="gate-icon">🟢</div>`, iconSize: [24, 24] }),
    }).addTo(map);
    m.bindTooltip(g.id, { permanent: true, direction: "top", offset: [0, -8], className: "officer-tip" });
    gateLayers[g.id] = m;
  });
  map.fitBounds([sw, ne], { padding: [30, 30] });
}

function buildCamPreviews() {
  const box = document.getElementById("cams");
  if (!box) return;
  box.innerHTML = "";
  (CFG.cameras || []).filter((c) => c.shot_url).forEach((c) => {
    const fig = document.createElement("figure");
    fig.className = "cam";
    fig.innerHTML = `<img alt="${c.id}"><figcaption>${c.id}</figcaption>` +
                    `<span class="zbadge">Zone ${c.zone_id || "?"}</span>`;
    box.appendChild(fig);
    const img = fig.querySelector("img");
    const refresh = () => {
      img.src = c.shot_url + (c.shot_url.includes("?") ? "&" : "?") + "t=" + Date.now();
    };
    refresh();
    setInterval(refresh, 1500);   // live preview; each phone frame is one GET
  });
}

function buildGatePanel() {
  const panel = $("gate-panel");
  panel.innerHTML = "";
  CFG.gates.forEach((g) => {
    const card = document.createElement("div");
    card.className = "gate-card";
    card.innerHTML = `<h3>${g.id} <span class="gate-state" id="gs-${g.id}">—</span></h3>
      <div class="gate-btns">${OVERRIDE_ACTIONS.map(
        (a) => `<button data-gate="${g.id}" data-action="${a}">${a.replace("CLOSE_DIVERT_LEFT", "CLOSE↩").replace("DIVERT_LEFT", "DIVERT")}</button>`
      ).join("")}</div>`;
    panel.appendChild(card);
  });
  panel.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => fetch("/api/gate/override", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gate_id: btn.dataset.gate, action: btn.dataset.action }),
    });
  });
}

function connectWS() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => setConn(true);
  ws.onclose = () => { setConn(false); setTimeout(connectWS, 1500); };
  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.kind === "snapshot") applySnapshot(data);
    else if (data.kind === "msg") onMsg(data.message);
  };
  // keepalive
  setInterval(() => { if (ws.readyState === 1) ws.send("ping"); }, 20000);
}

function setConn(ok) { $("conn-dot").className = "dot " + (ok ? "ok" : "bad"); }

function applySnapshot(d) {
  const s = d.state || {};
  Object.values(s.zones || {}).forEach(updateZone);
  Object.values(s.cameras || {}).forEach(updateCamera);
  Object.values(s.gates || {}).forEach(updateGate);
  Object.values(s.officers || {}).forEach(updateOfficer);
  if (s.advisory && s.advisory.en) updateAdvisory(s.advisory);
  (d.log || []).forEach((e) => addLog(e.type, e.payload, e.ts));
}

function onMsg(m) {
  const p = m.payload || {};
  switch (m.type) {
    case "zone.density.update": updateZone(p); break;
    case "camera.health": updateCamera(p); break;
    case "gate.telemetry": updateGate(p); break;
    case "officer.beacon": updateOfficer(p); break;
    case "venue.advisory": updateAdvisory(p); addLog(m.type, p, m.ts); break;
    case "gate.command": case "incident.report": case "dispatch.order":
      addLog(m.type, p, m.ts); break;
  }
}

function updateZone(p) {
  const layer = zoneLayers[p.zone_id];
  if (!layer) return;
  const color = RISK_COLOR[p.risk] || RISK_COLOR.UNKNOWN;
  layer.setStyle({ fillColor: color, fillOpacity: 0.45, color });
  const d = p.density_per_m2 == null ? "?" : p.density_per_m2;
  const cam = p.camera_id ? ` ← ${p.camera_id}` : "";
  const tag = p.risk === "UNKNOWN" ? "UNKNOWN (no view)" : p.risk;
  layer.setTooltipContent(`Zone ${p.zone_id}${cam} · ${d}/m² · ${tag}`);
}

function updateCamera(p) {
  const chips = $("chips");
  let chip = document.getElementById(`chip-${p.camera_id}`);
  if (!chip) {
    chip = document.createElement("div");
    chip.id = `chip-${p.camera_id}`;
    chips.appendChild(chip);
  }
  chip.className = "chip " + (p.state || "OK");
  chip.textContent = `${p.camera_id} · ${p.fps_effective ?? "?"}fps · ${p.state}`;
}

function updateGate(p) {
  gateState[p.gate_id] = p.state;
  const m = gateLayers[p.gate_id];
  if (m) m.setIcon(L.divIcon({ className: "", html: `<div class="gate-icon">${GATE_ICON[p.state] || "⬜"}</div>`, iconSize: [24, 24] }));
  const badge = document.getElementById(`gs-${p.gate_id}`);
  if (badge) { badge.textContent = p.state; badge.className = "gate-state " + p.state; }
}

function updateOfficer(p) {
  const ll = latlonToFloor(p.lat, p.lon);
  const color = p.status === "enroute" ? "#38bdf8" : "#16a34a";
  let m = officerLayers[p.officer_id];
  if (!m) {
    m = L.circleMarker(ll, { radius: 7, color: "#0b0f14", weight: 2, fillColor: color, fillOpacity: 1 }).addTo(map);
    officerLayers[p.officer_id] = m;
  }
  m.setLatLng(ll).setStyle({ fillColor: color });
  m.bindTooltip(`${p.officer_id} · ${p.status || "?"} · ${p.battery_pct ?? "?"}%`, { className: "officer-tip" });
}

let advAll = null;
function updateAdvisory(p) {
  advAll = p;
  $("advisory").classList.add("live");
  $("advisory-text").textContent = p.en || "—";
}
$("advisory").onclick = () => {
  if (!advAll) return;
  $("advisory-text").textContent = `EN: ${advAll.en}   ·   HI: ${advAll.hi || "—"}   ·   KN: ${advAll.kn || "—"}`;
};

function fmtTime(ts) {
  if (!ts) return "--:--:--";
  try { return ts.slice(11, 19); } catch { return "--:--:--"; }
}

function badge(txt, cls) { return `<span class="badge ${cls || ""}">${txt}</span>`; }

function addLog(type, p, ts) {
  const log = $("log");
  const e = document.createElement("div");
  const kind = { "gate.command": "gate", "dispatch.order": "dispatch",
                 "incident.report": "incident", "venue.advisory": "advisory" }[type] || "";
  e.className = "entry " + kind;
  let badges = "", reason = "";
  if (type === "gate.command") {
    reason = p.reason || "";
    if (p.playbook_id) badges += badge(p.playbook_id, "k");
    badges += badge(p.action || "", "");
    if (p.triggered_by) badges += badge(p.triggered_by, p.triggered_by === "operator-override" ? "ovr" : "");
  } else if (type === "incident.report") {
    reason = p.text || "";
    if (p.structured) badges += badge(p.structured.severity || "", "") + badge(p.structured.type || "", "");
    badges += badge("schema_valid:" + p.schema_valid, "");
    if (p.inference_backend) badges += badge(p.inference_backend, "backend " + p.inference_backend);
  } else if (type === "dispatch.order") {
    reason = `→ ${p.officer_id} · ${p.reason || ""}`;
    if (p.playbook_id) badges += badge(p.playbook_id, "k");
    if (p.eta_s != null) badges += badge("ETA " + p.eta_s + "s", "");
    if (p.triggered_by) badges += badge(p.triggered_by, "");
  } else if (type === "venue.advisory") {
    reason = p.en || "";
    if (p.inference_backend) badges += badge(p.inference_backend, "backend " + p.inference_backend);
    if (p.latency_ms != null) badges += badge(p.latency_ms + "ms", "");
  }
  e.innerHTML = `<div class="top"><span class="etype">${type}</span><span class="etime">${fmtTime(ts)}</span></div>
    ${reason ? `<div class="reason">${reason}</div>` : ""}<div class="badges">${badges}</div>`;
  log.prepend(e);
  while (log.children.length > 200) log.removeChild(log.lastChild);
}

function tickClock() {
  setInterval(() => {
    const d = new Date();
    $("clock").textContent = d.toTimeString().slice(0, 8);
  }, 1000);
}

init();

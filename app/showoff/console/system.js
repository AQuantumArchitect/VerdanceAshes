// System drawer: READY TO DROP, the feedback bundle, campaign controls (save / load /
// reset / refresh), the theaters list and the ρ diagnostics. Plus the how-to coach.
import { state, BOARDS, prettyMap, availableMaps, deployChoicesForMap, companySealed } from "./state.js";
import { api } from "./api.js";
import { $, esc, pretty, toast, logLine } from "./render.js";
import { beliefCountsForMap, focusMapAndRepaint } from "./board.js";
import { renderCompany, syncCrewFromHub, showCompanyIntro, hideCompanyIntro } from "./company.js";
import { pullHubState } from "./homecoming.js";

/* ---- READY TO DROP: one honest checklist from /api/health, polled every 5 s while open ---- */
const FIXES = {
  python: "Install Python 3.10+ from python.org",
  numpy: "Run SETUP.bat again (numpy is missing)",
  scipy: "Run SETUP.bat again (scipy is missing)",
  umwelt: "Belief engine not found — the map will show no belief; see INSTALL.md",
  bar: "Install Beyond All Reason and launch it once",
  engine: "Launch Beyond All Reason once so it installs an engine",
  mod: "Press Drop once — the kernel installs the campaign into BAR",
  map: "The next map downloads on Drop (keep the window open)",
  kernel: "Start PLAY.bat and keep its window open",
};
function readyRows(h) {
  if (!h) return [{ ok: false, label: "Campaign kernel", fix: FIXES.kernel }];
  const rows = [
    { ok: !!h.pythonOk, label: "Python " + (h.python || "?"), fix: FIXES.python },
    { ok: !!h.numpy, label: "numpy", fix: FIXES.numpy },
    { ok: !!h.scipy, label: "scipy", fix: FIXES.scipy },
    { ok: !!h.umwelt, label: "Belief engine", fix: FIXES.umwelt },
    { ok: !!h.barDataRoot, label: "Beyond All Reason found", fix: FIXES.bar },
    { ok: !!h.engine, label: "BAR engine", fix: FIXES.engine },
    { ok: !!h.modInstalled, label: "Campaign installed in BAR", fix: FIXES.mod },
  ];
  if (h.nextMap) rows.push({ ok: h.mapCached === true, label: "Map for the next drop · " + pretty(h.nextMap), fix: FIXES.map, soft: h.mapCached == null });
  rows.push({ ok: h.stateMission != null, label: h.stateMission != null ? ("Campaign save · mission " + h.stateMission) : "Campaign save", fix: "Press Reset to start a campaign" });
  return rows;
}
function paintReady(h) {
  const list = $("cc-ready-list");
  if (!list) return;
  list.innerHTML = readyRows(h).map(r => `<li class="cc-ready-row ${r.ok ? "ok" : (r.soft ? "soft" : "bad")}"><span class="cc-dot" aria-hidden="true"></span><span>${esc(r.label)}${r.ok ? "" : `<small>${esc(r.fix)}</small>`}</span></li>`).join("");
  const prog = $("cc-ready-progress");
  const p = h && h.provision;
  if (prog) {
    const dl = p && p.state === "downloading";
    prog.hidden = !dl;
    if (dl) {
      const pct = Math.max(0, Math.min(100, Number(p.percent) || 0));
      const mb = x => (Number(x || 0) / 1048576).toFixed(0);
      prog.textContent = `Downloading ${p.map || "map"} · ${pct}% (${mb(p.bytes)}/${mb(p.total)} MB)`;
    }
  }
}
let readyTimer = null;
async function pollReady() {
  const drawer = $("cc-system");
  if (!drawer || !drawer.open) return;
  try { const r = await api.health(); paintReady(r.ok ? r.data : null); }
  catch (_) { paintReady(null); }
}
export function installSystemDrawer() {
  const drawer = $("cc-system");
  drawer.addEventListener("toggle", () => {
    if (drawer.open) { pollReady(); readyTimer = setInterval(pollReady, 5000); }
    else if (readyTimer) { clearInterval(readyTimer); readyTimer = null; }
  });
  $("cc-feedback-export").onclick = exportFeedbackBundle;
  $("btn-sync-hub").onclick = refreshHub;
  $("btn-save-campaign").onclick = saveCampaign;
  $("btn-load-campaign").onclick = loadCampaign;
  $("btn-reset-campaign").onclick = resetCampaign;
}

async function exportFeedbackBundle() {
  const btn = $("cc-feedback-export");
  const out = $("cc-feedback-result");
  btn.disabled = true;
  out.hidden = false;
  out.textContent = "Packing…";
  try {
    const { data: j } = await api.feedbackBundle($("cc-feedback-notes").value || "");
    if (!j.ok) throw new Error(j.error || "bundle failed");
    out.textContent = "Saved: " + j.path + (j.skipped && j.skipped.length ? " · left out: " + j.skipped.join(", ") : "");
    toast("Feedback bundle saved — " + j.path, "ok");
  } catch (err) {
    out.textContent = "Could not export: " + err.message;
    toast("Feedback bundle: " + err.message, "err");
  } finally {
    btn.disabled = false;
  }
}

/* ---- campaign controls ------------------------------------------------------------- */
async function refreshHub() {
  if (!state.hostLive) return toast("Start PLAY.bat and keep its window open for a live map", "err");
  try {
    await api.rebuildHub();
    await pullHubState();
    toast("Map refreshed", "ok");
  } catch (e) {
    toast("Refresh failed: " + e.message, "err");
  }
}
function forgetLocalPicks() {
  state.crewBand = [];
  state.crewYou = null;
  state.sortieSynced = false;
  state.knownCompanyIds = null;
  state.selectedZoneId = null;
}
async function resetCampaign() {
  if (!state.hostLive) return toast("Open the wire first — or run RESET.bat from the workspace", "err");
  const typed = window.prompt(
    "FULL RESET (same as RESET.bat):\n" +
      "• backup then wipe campaign_state\n" +
      "• archive stale inbox/outbox results\n" +
      "• clear Act-N mission lua (stops naked-com ghosts)\n" +
      "• fresh mission 1 + starter Punch, metal 0×1km$\n\n" +
      "Type YES to confirm:", "");
  if (!typed || String(typed).trim().toUpperCase() !== "YES") return toast("Reset cancelled", "err");
  try {
    toast("Resetting campaign…");
    const { ok, data: j } = await api.resetCampaign();
    if (!ok || j.ok === false) return toast((j && (j.error || (j.reset && j.reset.error))) || "Reset failed", "err");
    forgetLocalPicks();
    await pullHubState();
    syncCrewFromHub();
    renderCompany();
    showCompanyIntro();
    const mn = (j && j.missionNumber) || (state.hub && state.hub.missionNumber) || 1;
    logLine("Campaign reset — mission " + mn + ". Form the company (pick 3 packs) before Drop.");
    toast("Campaign reset — pick your company to continue.", "ok");
  } catch (e) {
    toast("Reset failed: " + e.message, "err");
  }
}
async function saveCampaign() {
  if (!state.hostLive) return toast("Start PLAY.bat and keep its window open", "err");
  const mn = (state.hub && state.hub.missionNumber) || 1;
  const name = window.prompt(
    "Save campaign state to a named slot (state/saves/<name>/).\n" +
      "Letters, numbers, dash, underscore. Leave blank for a timestamped slot.", "mission_" + mn);
  if (name === null) return toast("Save cancelled", "err");
  try {
    toast("Saving…");
    const { ok, data: j } = await api.saveCampaign(String(name || "").trim());
    if (!ok || j.ok === false) return toast((j && j.error) || "Save failed", "err");
    const slot = (j && j.slot) || name || "?";
    logLine("Saved campaign → slot " + slot + " (mission " + ((j.meta && j.meta.missionNumber) || mn) + ")");
    toast("Saved as “" + slot + "”", "ok");
  } catch (e) {
    toast("Save failed: " + e.message, "err");
  }
}
async function loadCampaign() {
  if (!state.hostLive) return toast("Start PLAY.bat and keep its window open", "err");
  let saves = [];
  try {
    const { ok, data: j } = await api.saves();
    if (!ok || j.ok === false) throw new Error((j && j.error) || "Could not list saves");
    saves = j.saves || [];
  } catch (e) {
    return toast(e.message || "Could not list saves", "err");
  }
  if (!saves.length) return toast("No saves yet — hit Save first", "err");
  const listing = saves.map((s, i) => {
    const when = s.savedAt ? String(s.savedAt).replace("T", " ").replace("Z", "") : "?";
    return (i + 1) + ") " + (s.label || s.id) + "  ·  m" + (s.missionNumber ?? "?") + "  ·  " + when;
  }).join("\n");
  const pick = window.prompt("Load a save slot (overwrites live campaign_state; current state is backed up first).\n\n" + listing + "\n\nType the slot name (or number):", saves[0].id);
  if (pick === null) return toast("Load cancelled", "err");
  let slot = String(pick || "").trim();
  const asNum = Number(slot);
  if (Number.isInteger(asNum) && asNum >= 1 && asNum <= saves.length) slot = saves[asNum - 1].id;
  if (!slot) return toast("No slot chosen", "err");
  const typed = window.prompt("Load “" + slot + "” over the live campaign?\nType YES to confirm:", "");
  if (!typed || String(typed).trim().toUpperCase() !== "YES") return toast("Load cancelled", "err");
  try {
    toast("Loading “" + slot + "”…");
    const { ok, data: j } = await api.loadCampaign(slot);
    if (!ok || j.ok === false) return toast((j && j.error) || "Load failed", "err");
    forgetLocalPicks();
    await pullHubState();
    syncCrewFromHub();
    renderCompany();
    if (!companySealed()) showCompanyIntro(); else hideCompanyIntro();
    const mn = (j && j.missionNumber) || (state.hub && state.hub.missionNumber) || "?";
    logLine("Loaded save “" + slot + "” → mission " + mn);
    toast(companySealed() ? ("Loaded “" + slot + "” — company intact.") : ("Loaded “" + slot + "” — form the company before Drop."), "ok");
  } catch (e) {
    toast("Load failed: " + e.message, "err");
  }
}

/* ---- coach -------------------------------------------------------------------- */
export function showCoach(force) {
  try { if (!force && localStorage.getItem("va_coach_seen_v2") === "1") return; } catch (_) { /* private mode */ }
  $("coach").classList.add("show");
}
export function hideCoach(remember) {
  $("coach").classList.remove("show");
  if (remember) { try { localStorage.setItem("va_coach_seen_v2", "1"); } catch (_) { /* */ } }
}

/* ---- theaters (belief counts per map) ------------------------------------------------ */
export function renderRegions() {
  const focus = state.focusMap || (state.hub.node && state.hub.node.regionHint);
  const openIds = new Set(availableMaps());
  const el = $("regions");
  el.innerHTML = (state.hub.regions || []).map(r => {
    // Journey maps always open; builder selectable:false locks the rest.
    const locked = !openIds.has(r.mapId) && r.selectable === false;
    const cls = ["panel-card", "region", r.mapId === focus ? "focus" : "", locked ? "locked" : ""].filter(Boolean).join(" ");
    const n = deployChoicesForMap(r.mapId).length;
    const bc = beliefCountsForMap(r.mapId);
    return `<div class="${cls}" data-map="${esc(r.mapId)}" data-locked="${locked ? "1" : "0"}">
        <div class="name">${esc(r.displayName || r.mapId)}</div>
        <div class="meta">${esc(r.descriptor || r.family)}${n ? ` · ${n} sortie${n === 1 ? "" : "s"}` : ""}</div>
        <div class="row belief-counts" title="What the company believes about this ground: looked at recently / looked at once / nobody has looked">
          <span class="bc-known">● ${bc.current} known</span>
          <span class="bc-stale">◐ ${bc.stale} stale</span>
          <span class="bc-dark">? ${bc.dark} dark</span>
          ${locked ? `<span class="ctrl">locked</span>` : ""}
        </div>
      </div>`;
  }).join("");
  el.querySelectorAll(".region").forEach(card => {
    card.onclick = () => {
      if (card.dataset.locked === "1") return toast("That theater is not open yet — finish nearer objectives", "err");
      focusMapAndRepaint(card.dataset.map, "Focus theater");
    };
  });
}

/* ---- ρ diagnostics (war-map density matrix) --------------------------------------------- */
// Heat from dark green to gold, as a mix of the tokens.
const heatColor = (v) => `color-mix(in srgb, var(--gold) ${Math.round(Math.max(0, Math.min(1, v)) * 100)}%, var(--panel-raised))`;
function buildRho(mapId) {
  const zones = ((BOARDS[mapId] || {}).zones) || [];
  if (!zones.length) return { labels: [], matrix: [], zones: [] };
  const n = zones.length;
  const centers = zones.map(z => {
    const b = z.bounds || {};
    return { x: ((b.xMin || 0) + (b.xMax || 1)) / 2, z: ((b.zMin || 0) + (b.zMax || 1)) / 2, zone: z };
  });
  const matrix = Array.from({ length: n }, () => Array(n).fill(0));
  const g = state.hub.graph || {};
  const contest = Math.min(1.5, Number(g.q6_contested) || 0.85);
  const voidS = Number(g.q2_void_structure) || 0.15;
  for (let i = 0; i < n; i++) {
    const ctrl = (zones[i].control || zones[i].defaultControl || "neutral");
    matrix[i][i] = Math.min(1, 0.35 + 0.4 * contest * (ctrl === "contested" || ctrl === "armada" ? 1 : 0.6));
    for (let j = i + 1; j < n; j++) {
      const dx = centers[i].x - centers[j].x, dz = centers[i].z - centers[j].z;
      const dist = Math.sqrt(dx * dx + dz * dz) || 0.01;
      let coh = Math.exp(-dist * (2.2 + voidS * 2)) * contest * 0.85;
      if (zones[i].capturable && zones[j].capturable) coh *= 1.15;
      coh = Math.min(0.95, coh);
      matrix[i][j] = coh;
      matrix[j][i] = coh;
    }
  }
  let mx = 0.001;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) mx = Math.max(mx, matrix[i][j]);
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) matrix[i][j] = matrix[i][j] / mx;
  return { labels: zones.map(z => (z.label || z.zoneId || "?").slice(0, 10)), matrix, zones, centers };
}
export function renderQuantum() {
  const mapId = state.focusMap || state.hub.sessionHomeMap || (state.hub.node && state.hub.node.regionHint) || ((state.hub.regions || [])[0] && (state.hub.regions || [])[0].mapId);
  const g = state.hub.graph || {};
  const rhoCamp = state.hub.campaignRho || {};
  const axes = rhoCamp.axes || {};
  const keys = [
    ["Armada↔Cortex", g.q0_armada_cortex], ["Void scars", g.q2_void_structure], ["Contested", g.q6_contested],
    ["Independents", g.q6_independent], ["Scarcity", g.q7_resource_scarcity],
  ];
  if (axes.arm_cor != null) keys.push(["Faction pull", axes.arm_cor], ["Path tilt", axes.phi], ["Tenebrium pressure", axes.tenebrium]);
  $("graph-scalars").innerHTML = keys.map(([k, v]) => `<span class="scalar-pill">${k} <b>${Number(v || 0).toFixed(2)}</b></span>`).join("");
  const sp = state.hub.spectral || {};
  const energy = Number(sp.energy || keys.reduce((s, [, v]) => s + Math.abs(Number(v || 0)), 0));
  $("spec-bar").innerHTML = `<i style="width:${Math.min(100, Math.round((energy / 6) * 100))}%"></i>`;
  const pur = rhoCamp.purity != null ? Number(rhoCamp.purity).toFixed(2) : "—";
  const ent = rhoCamp.entropy != null ? Number(rhoCamp.entropy).toFixed(2) : "—";
  $("spec-meta").textContent = `Theater: ${prettyMap(mapId)} · war energy ${energy.toFixed(2)} · focus ${pur} · chaos ${ent}`;
  const adv = $("rho-advanced");
  if (adv) {
    adv.textContent =
      `q0=${Number(g.q0_armada_cortex || 0).toFixed(3)} q2=${Number(g.q2_void_structure || 0).toFixed(3)} ` +
      `q6c=${Number(g.q6_contested || 0).toFixed(3)} q7=${Number(g.q7_resource_scarcity || 0).toFixed(3)} ` +
      `λ=${Number(sp.dominantEigenvalue || 0).toFixed(3)} path=${state.hub.pathSignal || "B"}`;
  }
  const rho = buildRho(mapId);
  const n = rho.matrix.length;
  if (!n) {
    $("rho-table").innerHTML = "<tr><td class='empty'>No zone board — run build_zone_boards_v1.py</td></tr>";
    $("ent-svg").innerHTML = "";
    $("rho-inspect").textContent = "";
    return;
  }
  state.rhoSel.i = Math.min(state.rhoSel.i, n - 1);
  state.rhoSel.j = Math.min(state.rhoSel.j, n - 1);
  let body = "<tr><th></th>" + rho.labels.map(l => `<th title="${esc(l)}">${esc(l.slice(0, 4))}</th>`).join("") + "</tr>";
  for (let i = 0; i < n; i++) {
    body += `<tr><th title="${esc(rho.labels[i])}">${esc(rho.labels[i].slice(0, 4))}</th>`;
    for (let j = 0; j < n; j++) {
      const v = rho.matrix[i][j];
      const sel = (state.rhoSel.i === i && state.rhoSel.j === j) ? " sel" : "";
      body += `<td class="${sel}" data-i="${i}" data-j="${j}" style="background:${heatColor(v)}" title="${v.toFixed(3)}"></td>`;
    }
    body += "</tr>";
  }
  $("rho-table").innerHTML = body;
  $("rho-table").querySelectorAll("td[data-i]").forEach(td => {
    td.onclick = () => { state.rhoSel = { i: +td.dataset.i, j: +td.dataset.j }; renderQuantum(); };
  });
  const si = state.rhoSel.i, sj = state.rhoSel.j;
  $("rho-inspect").textContent = `Link ${rho.matrix[si][sj].toFixed(2)} · ${rho.labels[si]} ↔ ${rho.labels[sj]}`;
  // Entanglement SVG — edges for strong off-diagonals
  const W = 280, Hh = 140, pad = 18;
  const pts = (rho.centers || []).map((c, idx) => ({ x: pad + c.x * (W - 2 * pad), y: pad + c.z * (Hh - 2 * pad), i: idx }));
  let edges = "";
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const v = rho.matrix[i][j];
      if (v < 0.35) continue;
      edges += `<line x1="${pts[i].x}" y1="${pts[i].y}" x2="${pts[j].x}" y2="${pts[j].y}" stroke-opacity="${(0.15 + v * 0.7).toFixed(3)}" stroke-width="${0.6 + v * 2.2}"/>`;
    }
  }
  const nodes = pts.map((p, i) => {
    const hot = i === si || i === sj;
    return `<circle cx="${p.x}" cy="${p.y}" r="${hot ? 5.5 : 3.5}" fill="${hot ? "var(--gold)" : "var(--edge)"}" opacity="0.9"/>`;
  }).join("");
  $("ent-svg").innerHTML = edges + nodes;
}

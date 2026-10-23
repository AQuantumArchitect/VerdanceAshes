// System drawer: READY TO DROP, the feedback bundle, campaign controls (save / load /
// reset / refresh), the theaters list and the ρ diagnostics. Plus the how-to coach.
import { state, availableMaps, deployChoicesForMap, companySealed } from "./state.js";
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

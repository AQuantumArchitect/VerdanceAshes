// Operations: the drop plan, the confirm sheet, the warm (level loading) poll and the stamp.
import { state, BOARDS, commerce, companySealed, prettyMap, jobLabel, arcMax, deployChoicesForMap, ensureFocusMapAvailable } from "./state.js";
import { api } from "./api.js";
import { $, esc, toast, logLine, downloadJson, renderHeroCard, crewHeroName } from "./render.js";
import { defaultMarks, snapGroundRoute, isLegalLanding, padLegality, padExposed, renderBoard, renderMapPicker } from "./board.js";
import { renderCompany, buildCompanyEntries, crewCoreIds, droppingPackIds, sealedDeployAces, livingCoreIds, heroIsDeployable, heroAway, heroWhereLabel, companyOwnedBand, showCompanyIntro, hideCompanyIntro } from "./company.js";
import { renderBadges } from "./shell.js";
import { hideCoach } from "./system.js";
import { renderReserve, reserveBring, resetReserveBring } from "./reserve.js";

/* ---- plan ------------------------------------------------------------------- */
export function ensureTheaterPlan(choice) {
  const effect = (choice && choice.effect) || {};
  const mapId = effect.mapId || state.focusMap || state.hub.sessionHomeMap || (state.hub.node && state.hub.node.regionHint) || "the_rock_jungle";
  const marks = defaultMarks(mapId);
  if (effect.preferredCaptureZoneId) marks.captureZoneIds = [effect.preferredCaptureZoneId];
  if (effect.captureZoneIds && effect.captureZoneIds.length) marks.captureZoneIds = effect.captureZoneIds.slice();
  const preferredDeploy = effect.preferredDeployZoneId || effect.deploymentZoneId;
  const camp = state.hub.camp || {};
  const campPadHere = !!(camp.nextPadZoneId && (!camp.nextPadMapId || camp.nextPadMapId === mapId)
    && ((BOARDS[mapId] || {}).zones || []).some(z => z.zoneId === camp.nextPadZoneId));
  // The camp's own next pad (where the company actually is) outranks an authored pad.
  // Honor story/engine pads even when midfield — LZ legality is stamp-side.
  // A road card stands on a door (the far door of a crossing, or the door you hold on this
  // map): that pad is the point of the sortie, so neither the camp pad nor the snap moves it.
  const padLocked = !!(effect.padLocked && preferredDeploy);
  if (preferredDeploy && (padLocked || !campPadHere)) marks.deployZoneId = preferredDeploy;
  // ONE PAD: authored extraction/exfil pads are ignored. You leave from where you landed.
  marks.extractZoneId = marks.deployZoneId;
  const against = effect.against || (mapId === "eye_of_horus" ? "cortex" : mapId === "the_rock_jungle" ? "wild" : "armada");
  state.plan = {
    schemaVersion: "verdance-deploy-plan/1.0",
    mapId,
    contractKind: effect.contractKind || (mapId === "the_rock_jungle" ? "hive_clear_or_bypass" : "seize_lane"),
    deployAces: sealedDeployAces(), // packs currently in Dropping
    crewBand: state.crewBand.slice(),
    choiceId: (choice && choice.id) || "c_theater",
    repDelta: effect.repDelta || {},
    arcId: (state.hub.arc && state.hub.arc.id) || 1,
    maxCaptureMarks: arcMax(),
    marks,
    pathSignal: state.hub.pathSignal,
    sessionMode: effect.sessionMode || state.hub.sessionMode || "same_map",
    occupationModel: state.hub.occupationModel || "living_shell",
    commerceDeploy: { tenebrium: commerce().tenebrium, kit: commerce().deployKit || [] },
    patron: "nullmercs",
    against,
  };
  if (!padLocked) snapGroundRoute(mapId, marks);
  state.markMode = state.markMode || "capture";
  state.focusMap = mapId;
  return state.plan;
}

export function openDeploy(choice) {
  ensureTheaterPlan(choice);
  state.markMode = "capture";
  document.querySelectorAll(".mode-btn").forEach(b => b.classList.toggle("active", b.dataset.mode === state.markMode));
  updateDeployGate();
  renderMapPicker(); // the plan may have moved the focus map
  renderBoard();
  logLine(`Route briefing — ${prettyMap(state.plan.mapId)} · ${jobLabel(state.plan.contractKind)}`);
  toast(`Mark the target on ${prettyMap(state.plan.mapId)}`, "ok");
  const th = $("theater");
  if (th) th.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// The rail and the matters inspector select an operation by its choice id.
export function onChoice(id) {
  const ch = ((state.hub.node || {}).choices || []).find(c => c.id === id);
  if (!ch || ch.kind !== "deploy") return;
  openDeploy(ch);
}

export function refreshTheaterForFocus() {
  const mapId = ensureFocusMapAvailable() || state.focusMap || state.hub.sessionHomeMap || (state.hub.node && state.hub.node.regionHint) || "the_rock_jungle";
  const prevMap = state.plan && state.plan.mapId;
  const match = deployChoicesForMap(mapId)[0] || null; // prefer a deploy choice matching this map
  ensureTheaterPlan(match || { id: "c_theater", effect: { mapId } });
  if (prevMap && prevMap !== mapId) state.selectedZoneId = null; // drop zone selection when the map changes
  renderMapPicker();
  renderBoard();
  renderCompany();
}

/* ---- deploy gate --------------------------------------------------------------- */
function dropBlockReason() {
  if (!companySealed()) return "Form the company first";
  const plan = state.plan;
  if (!plan) return "Pick a sortie on the map first";
  const m = plan.marks || {};
  if (!(m.captureZoneIds && m.captureZoneIds.length)) return "Mark a target on the map first";
  if (!m.deployZoneId) return "Mark the pad first";
  return "";
}
export function updateDeployGate() {
  const btn = $("btn-deploy");
  if (!btn) return;
  const warmPhase = state.warm && state.warm.phase;
  if (warmPhase === "up") {
    btn.disabled = false;
    btn.classList.add("dropping");
    btn.title = "Recoil is open. This returns to the confirm screen.";
    btn.textContent = "Recoil is open";
    return;
  }
  if (state.dropping || warmPhase === "loading") {
    btn.disabled = false;
    btn.classList.add("dropping");
    btn.title = "The level is loading. Open the confirm screen to see who is shipping.";
    btn.textContent = "Recoil is loading…";
    return;
  }
  btn.classList.remove("dropping");
  btn.disabled = false; // unsealed: the button opens the company picker
  if (!companySealed()) {
    btn.title = "Open the company picker — pick 3 packs, then Confirm";
    btn.textContent = "Form company to Drop";
    return;
  }
  const packs = droppingPackIds().length;
  const coreN = livingCoreIds().length;
  const roster = `${packs} pack${packs === 1 ? "" : "s"} + ${coreN} core`;
  const block = dropBlockReason();
  if (block) {
    btn.title = block;
    btn.textContent = block;
    return;
  }
  btn.title = `This drop ships ${roster}. Core always comes. Choose who deploys after pressing Launch.`;
  btn.textContent = state.hostLive ? `Launch · ${roster}` : `Save plan · ${roster}`;
}

/* ---- drop confirm sheet + warm poll ---------------------------------------------- */
export function dropRosterSealed() {
  const phase = state.warm && state.warm.phase;
  return phase === "loading" || phase === "sealing" || phase === "up"; // locked on Confirm drop, before the level compiles
}
function dropConfirmOpen() {
  const el = $("drop-confirm");
  return !!(el && el.classList.contains("show"));
}
export function hideDropConfirm() {
  const el = $("drop-confirm");
  if (el) el.classList.remove("show");
  if (state.warm && state.warm.timer) {
    clearTimeout(state.warm.timer);
    state.warm.timer = null;
  }
}
function paintWarmStatus(text) {
  const el = $("drop-warm-status");
  if (!el) return;
  const phase = state.warm && state.warm.phase;
  el.textContent = text || (
    phase === "up" ? "Recoil is open with this company."
    : (phase === "sealing" || phase === "loading") ? "Dropping… The company is locked. The level loads with that roster."
    : phase === "failed" ? "The load did not start. Adjust the company and try again."
    : "Pick who ships, then press Confirm drop. Nothing loads until the company is locked."
  );
}
export function noteRosterChanged() {
  if (!dropConfirmOpen()) return;
  renderDropSquad();
  paintWarmStatus();
}
function sessionIsThisDrop(st) {
  const started = state.warm && state.warm.startedAt;
  if (!started) return false;
  const updated = Date.parse((st && st.updatedAt) || "") || 0;
  return updated + 2000 >= started;
}
export function renderDropSquad() {
  renderReserve(dropRosterSealed());
  const squadEl = $("drop-squad");
  const kicker = $("drop-squad-kicker");
  const go = $("drop-confirm-go");
  const coreIds = crewCoreIds();
  const entries = buildCompanyEntries().filter(e => e.tier === "deployed" || e.tier === "base");
  const packN = droppingPackIds().length;
  const coreN = livingCoreIds().length;
  if (kicker) kicker.textContent = entries.length ? `Who is dropping · ${packN} pack${packN === 1 ? "" : "s"} + ${coreN} core` : "Who is dropping · core only";
  if (squadEl) {
    const locked = dropRosterSealed();
    const cards = entries.map(e => {
      const isCore = coreIds.includes(e.id);
      const on = e.tier === "deployed";
      const canToggle = !isCore && !!e.pickable && !locked;
      return renderHeroCard({
        id: e.id, ace: e.ace,
        tag: isCore ? "core · always" : (on ? "dropping" : "at base"),
        classes: [isCore ? "core" : "", on ? "on" : "tier-base", canToggle ? "toggleable" : ""].filter(Boolean),
        compact: true, hideCost: true, dataCrew: canToggle ? e.id : null, disabled: !canToggle, type: "button",
      });
    });
    const notBoarding = companyOwnedBand().concat(coreIds).filter((id, i, arr) => arr.indexOf(id) === i && !heroIsDeployable(id));
    const away = notBoarding.filter(heroAway);
    const fallenHome = notBoarding.filter(id => !heroAway(id));
    let html = cards.join("") || `<div class="theater-sub">Nobody living is marked to drop.</div>`;
    if (away.length) html += `<div class="theater-sub spaced">Away from camp · ${away.map(id => `${esc(crewHeroName(id))} (${esc(heroWhereLabel(id))})`).join(" · ")}</div>`;
    if (fallenHome.length) html += `<div class="theater-sub spaced">Fallen stay home · ${fallenHome.map(crewHeroName).map(esc).join(" · ")}</div>`;
    squadEl.innerHTML = html;
  }
  if (go) {
    const phase = state.warm && state.warm.phase;
    go.disabled = phase === "loading" || phase === "sealing";
    go.textContent = phase === "up" ? "Back to the map"
      : (phase === "sealing" || phase === "loading") ? "Dropping…"
      : phase === "failed" ? "Try the drop again"
      : "Confirm drop";
  }
}
function pollWarm() {
  if (state.warm.poll) clearTimeout(state.warm.poll);
  const fail = (msg, statusMsg) => {
    state.warm.locked = false;
    state.warm.phase = "failed";
    paintWarmStatus(statusMsg || msg);
    blockDrop(msg);
    renderDropSquad();
    updateDeployGate();
  };
  const tick = async () => {
    if (!state.warm || (state.warm.phase !== "loading" && state.warm.phase !== "sealing" && state.warm.phase !== "up")) return;
    try {
      const status = (await api.status()).data || {};
      const deployPhase = String(status.deployPhase || "");
      if (state.warm.phase === "loading" && deployPhase === "idle" && !status.busy) {
        return fail("The load stopped before Recoil opened. Try the drop again.", "The load stopped. Adjust the company and try again.");
      }
      if (state.warm.phase === "loading" && (deployPhase === "sealing" || deployPhase === "launching")) {
        state.warm.phase = "sealing";
        state.warm.locked = true;
        paintWarmStatus();
        renderDropSquad();
        updateDeployGate();
      }
      if (deployPhase === "failed" && state.warm.phase !== "up") {
        return fail(String(status.error || (status.lastDeploy && status.lastDeploy.error) || "The load did not start."));
      }
      const st = ((await api.session()).data || {}).status || {};
      if (sessionIsThisDrop(st)) {
        const phase = String(st.phase || "");
        const loadingPhase = phase === "building" || phase === "preflight" || phase === "starting" || phase === "dropping";
        // in-game is written only after the level is actually in. A spring pid by itself is still the load.
        if (phase === "in-game" && st.springPid) {
          const first = state.warm.phase !== "up";
          state.warm.phase = "up";
          state.warm.locked = true;
          paintWarmStatus("Recoil is open with this company.");
          renderDropSquad();
          updateDeployGate();
          if (first) toast("Recoil is open.", "ok");
          state.warm.poll = setTimeout(tick, 3000);
          return;
        }
        if (loadingPhase) {
          state.warm.locked = true;
          if (state.warm.phase === "loading") state.warm.phase = "sealing";
          paintWarmStatus("Dropping… The company is locked. The level is loading.");
          renderDropSquad();
          updateDeployGate();
        }
        if (state.warm.phase === "up" && phase && !loadingPhase && phase !== "in-game") {
          state.warm.phase = "idle";
          state.warm.locked = false;
          paintWarmStatus("Recoil has closed. Choose who ships, then press Confirm drop.");
          renderDropSquad();
          updateDeployGate();
          return;
        }
        if (st.error && state.warm.phase !== "up") return fail(String(st.error));
      }
    } catch (_) { /* keep waiting */ }
    state.warm.poll = setTimeout(tick, 2000);
  };
  state.warm.poll = setTimeout(tick, 1200);
}
async function noteSpringAlreadyOpen() {
  if (!state.hostLive || !state.warm || (state.warm.phase !== "idle" && state.warm.phase !== "failed")) return;
  try {
    const st = ((await api.session()).data || {}).status || {};
    if (!state.warm || (state.warm.phase !== "idle" && state.warm.phase !== "failed")) return;
    const phase = String(st.phase || "");
    if (st.springPid || phase === "in-game" || phase === "dropping") {
      paintWarmStatus("Recoil is still open from the last fight. Close it, then press Confirm drop. The company locks on that press, and only then does the level load.");
    }
  } catch (_) { /* sheet stays idle */ }
}
export function showDropConfirm() {
  hideCoach(false);
  hideCompanyIntro();
  if (!companySealed()) {
    showCompanyIntro();
    return toast("Pick 3 packs and Confirm company first", "warn");
  }
  const plan = state.plan;
  if (!plan) return toast("Mark a route on the theater first", "err");
  if (!(plan.marks && plan.marks.captureZoneIds && plan.marks.captureZoneIds.length)) return toast("Mark a target (wound) on the map first", "err");
  if (!plan.marks.deployZoneId) return toast("Mark an authored deployment zone", "err");
  const zones = (BOARDS[plan.mapId] || {}).zones || [];
  const zoneName = (id) => {
    if (!id) return "—";
    const z = zones.find(x => x.zoneId === id);
    return (z && z.label) || id;
  };
  const m = plan.marks || {};
  m.extractZoneId = m.deployZoneId; // one pad: the stamp carries deploy = extract = the same zone
  const targets = (m.captureZoneIds || []).map(zoneName).join(", ") || "—";
  const body = $("drop-confirm-body");
  if (body) {
    const eyes = padExposed(m.deployZoneId);
    body.innerHTML =
      `Drop on <b>${esc(prettyMap(plan.mapId))}</b> · <b>${esc(jobLabel(plan.contractKind))}</b><br>` +
      `Pad <b>${esc(zoneName(m.deployZoneId))}</b> → wound <b>${esc(targets)}</b> → back to <b>${esc(zoneName(m.deployZoneId))}</b>.` +
      (eyes === "known" ? `<br><span class="bad">Armada has eyes on this pad.</span>` : "") +
      `<p>Get what you want onto the pad and press EXTRACT. What is off the pad stays. What stays becomes a holding.</p><p>Engine launch starts after you confirm this deployment.</p>`;
    body.setAttribute("data-route", body.innerHTML);
  }
  const el = $("drop-confirm");
  if (el) el.classList.add("show");
  const phase = state.warm && state.warm.phase;
  if (phase === "loading" || phase === "sealing") {
    renderDropSquad();
    paintWarmStatus();
    return;
  }
  if (phase !== "up") {
    resetReserveBring();
    state.warm.phase = "idle";
    state.warm.locked = false;
    if (state.warm.timer) {
      clearTimeout(state.warm.timer);
      state.warm.timer = null;
    }
  }
  renderDropSquad();
  paintWarmStatus();
  if (state.warm.phase === "idle" || state.warm.phase === "failed") noteSpringAlreadyOpen();
}
export function onDropConfirmGo() {
  const phase = state.warm && state.warm.phase;
  if (phase === "up") return hideDropConfirm();
  if (phase === "loading" || phase === "sealing" || state.dropping) return paintWarmStatus();
  if (state.warm && state.warm.timer) {
    clearTimeout(state.warm.timer);
    state.warm.timer = null;
  }
  commitDeploy(true);
}

/* ---- stamp ------------------------------------------------------------------- */
function authoredPads(plan) {
  const ch = ((state.hub.node || {}).choices || []).find(c => c && c.id === (plan && plan.choiceId));
  const e = (ch && ch.effect) || {};
  // One pad: only authored landing pads count. Authored exfil fields are ignored.
  return new Set([e.preferredDeployZoneId, e.deploymentZoneId].filter(Boolean).map(String));
}
function canLaunchFrom(plan, z) {
  if (!z) return false;
  if (isLegalLanding(plan.mapId, z)) return true;
  // Recommended sorties stamp their own infil. The client used to reject those pads and
  // hide the toast under this dialog, so Confirm did nothing.
  return authoredPads(plan).has(String(z.zoneId));
}
function blockDrop(msg) {
  toast(msg, "err");
  const body = $("drop-confirm-body");
  if (body) {
    const base = body.getAttribute("data-route") || body.innerHTML;
    body.innerHTML = base + `<br><b class="bad">${esc(msg)}</b>`;
  }
  const el = $("drop-confirm");
  if (el) el.classList.add("show");
}
async function commitDeploy(launch) {
  const plan = state.plan;
  if (!plan) return blockDrop("Pick a sortie on the map first");
  if (!companySealed()) return blockDrop("Form the company first — pick 3 packs and Confirm");
  if (state.dropping) return;
  // Drop roster = packs marked Dropping. Core is added server-side and here.
  plan.crewBand = droppingPackIds();
  plan.deployAces = sealedDeployAces();
  plan.reserveBring = { ...reserveBring() };
  if (!(plan.marks && plan.marks.captureZoneIds && plan.marks.captureZoneIds.length)) return blockDrop("Mark a target (wound) on the map first");
  if (!plan.marks.deployZoneId) return blockDrop("Mark a pad first");
  plan.marks.extractZoneId = plan.marks.deployZoneId; // ONE pad
  const zones = (BOARDS[plan.mapId] || {}).zones || [];
  const dep = zones.find(z => z.zoneId === plan.marks.deployZoneId);
  if (!dep || !canLaunchFrom(plan, dep)) {
    const why = dep ? padLegality(plan.mapId, dep).why : "no such zone";
    return blockDrop(`The pad must be believed ours, a quiet rim, or the camp's next pad — ${why}`);
  }
  plan.commerceDeploy = { tenebrium: commerce().tenebrium, kit: commerce().deployKit || [] };
  if (state.warm && (state.warm.phase === "loading" || state.warm.phase === "sealing" || state.warm.phase === "up")) {
    paintWarmStatus();
    return;
  }
  const sheet = $("drop-confirm");
  if (sheet) sheet.classList.add("show");
  state.dropping = true;
  state.warm.locked = true;
  state.warm.phase = "loading";
  state.warm.startedAt = Date.now();
  renderDropSquad();
  paintWarmStatus();
  updateDeployGate();

  if (state.hostLive) {
    try {
      toast(launch ? "Dropping… The company is locked." : "Sealing the drop…");
      const { status, data } = await api.deploy(plan, launch);
      const accepted = !!(data && data.accepted);
      const launched = !!(data.launch && data.launch.ok && !data.launch.skipped);
      const reason = (data && (data.error || data.reason || (data.launch && data.launch.reason))) || "";
      if (!accepted && !launched) {
        state.warm.locked = false;
        state.warm.phase = "failed";
        const err = reason || `Drop failed (${status})`;
        logLine(err);
        paintWarmStatus(err);
        blockDrop(err);
        return;
      }
      logLine(`Loading ${prettyMap(plan.mapId)}. Recoil will open when the level is ready.`);
      state.hub.flags = state.hub.flags || {};
      state.hub.flags.deployStub = false;
      state.hub.lastResult = { kind: "deploy_committed", at: new Date().toISOString(), seedHint: data.seedHint };
      renderBadges();
      pollWarm();
    } catch (e) {
      state.warm.locked = false;
      state.warm.phase = "failed";
      paintWarmStatus("Wire error: " + e.message);
      blockDrop("Wire error: " + e.message);
    } finally {
      state.dropping = false;
      updateDeployGate();
      renderDropSquad();
    }
    return;
  }

  state.dropping = false;
  state.warm.locked = false;
  state.warm.phase = "idle";
  // Map-only: download the plan and point at PLAY.bat.
  try {
    downloadJson("hub_deploy_plan.json", plan);
    logLine(`Map-only plan for ${prettyMap(plan.mapId)}. Start PLAY.bat and keep its window open to fight.`);
    toast("Map only — start PLAY.bat and keep its window open to drop for real.", "err");
    state.hub.lastResult = { kind: "deploy_stub", mapId: plan.mapId, contractKind: plan.contractKind };
  } finally {
    state.dropping = false;
    updateDeployGate();
  }
}

export function resetRoute() {
  if (!state.plan) return;
  state.plan.marks = defaultMarks(state.plan.mapId);
  renderBoard();
  toast("Route reset", "ok");
}
export function setMarkMode(btn) {
  state.markMode = btn.dataset.mode;
  document.querySelectorAll(".mode-btn").forEach(b => b.classList.toggle("active", b === btn));
  renderBoard();
}

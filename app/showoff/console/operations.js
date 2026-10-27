// Operations: the drop plan, the confirm sheet, the warm (level loading) poll and the stamp.
import { state, BOARDS, commerce, companySealed, prettyMap, jobLabel, arcMax, deployChoicesForMap, ensureFocusMapAvailable } from "./state.js";
import { api } from "./api.js";
import { $, esc, toast, logLine, downloadJson, renderHeroCard, crewHeroName } from "./render.js";
import { defaultMarks, snapGroundRoute, isLegalLanding, padLegality, padExposed, renderBoard, renderMapPicker } from "./board.js";
import { rentedIds, renderShop, recomputeShopAvailability, storeWantsAttention, firstDrop, renderCompany, buildCompanyEntries, crewCoreIds, droppingPackIds, sealedDeployAces, livingCoreIds, heroIsDeployable, heroAway, heroWhereLabel, companyOwnedBand, showCompanyIntro, hideCompanyIntro } from "./company.js";
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
  const phase = state.warm && state.warm.phase;
  btn.classList.toggle("dropping", phase === "loading" || phase === "ready" || phase === "dropping" || phase === "up");
  btn.disabled = false;
  if (phase === "up") {
    btn.title = "The company is in the field. This opens the drop sheet.";
    btn.textContent = "In the field";
    return;
  }
  if (phase === "loading" || phase === "ready" || phase === "dropping") {
    btn.title = "The field is loaded (or loading) behind this screen. Open the sheet to pick who goes and drop.";
    btn.textContent = phase === "loading" ? "Field loading… pick who goes" : "Field ready · pick who goes";
    return;
  }
  if (!companySealed()) {
    btn.title = "Open the company picker — pick 3 packs, then Confirm";
    btn.textContent = "Form company to Drop";
    return;
  }
  const block = dropBlockReason();
  if (block) {
    btn.title = block;
    btn.textContent = block;
    return;
  }
  btn.title = "Load this field now. You pick who goes while it loads, then drop them in.";
  btn.textContent = state.hostLive ? "Launch" : "Save plan";
}

/* ---- the drop sheet: the field loads while you pick who goes (hot drop) ------------ */
// Phases: idle → loading (the kernel built and started BAR; packs still open) → ready (the field
// is in, paused, nobody of ours on it) → dropping → up (the company is in). The roster locks only
// at the drop. tools/verdance_kernel/hot_drop.py has the other half.
export function dropRosterSealed() {
  const phase = state.warm && state.warm.phase;
  return phase === "dropping" || phase === "up";
}
function dropConfirmOpen() {
  const el = $("drop-confirm");
  return !!(el && el.classList.contains("show"));
}
export function hideDropConfirm() {
  // Closing the sheet leaves a loading field loading: reopening it picks up where it was.
  const el = $("drop-confirm");
  if (el) el.classList.remove("show");
}
function setWarm(phase, text) {
  state.warm.phase = phase;
  state.warm.locked = phase === "dropping" || phase === "up";
  paintWarmStatus(text);
  renderDropSquad();
  renderShop();          // the store locks while the field loads
  updateDeployGate();
}
// The drop window's three windows: the party, the reserve kits, the Cortex mercenary store.
export function showDropTab(name) {
  document.querySelectorAll("[data-drop-tab]").forEach(b => b.classList.toggle("on", b.dataset.dropTab === name));
  document.querySelectorAll("[data-drop-win]").forEach(w => w.classList.toggle("on", w.dataset.dropWin === name));
}
function paintWarmStatus(text) {
  const el = $("drop-warm-status");
  if (!el) return;
  const phase = state.warm && state.warm.phase;
  el.textContent = text || (
    phase === "loading" ? `Loading ${prettyMap((state.plan || {}).mapId)} in Beyond All Reason behind this screen. Pick who goes; Drop wakes when the field is ready.`
    : phase === "ready" ? "The field is loaded and paused, the enemy in place. Your company lands the moment you drop."
    : phase === "dropping" ? "Dropping… the company is landing on the pad."
    : phase === "up" ? "The company is down on the pad, the field paused. Switch to Beyond All Reason and unpause when you are ready."
    : phase === "failed" ? "The field did not load. Adjust the route and try again."
    : "Launch loads the field now. You pick who goes while it loads."
  );
}
export function noteRosterChanged() {
  if (!dropConfirmOpen()) return;
  renderDropSquad();
  paintWarmStatus();
}
// A kings' showdown (hub.theaters, from verdance.world.theaters): the commander walks out alone.
function soloCommand(mapId) { return ((state.hub.theaters || {})[mapId] || {}).kind === "kings_showdown"; }
export function renderDropSquad() {
  if (state.plan && soloCommand(state.plan.mapId)) {
    const squadEl = $("drop-squad"), kicker = $("drop-squad-kicker");
    if (kicker) kicker.textContent = "Who is dropping · the commander alone";
    const t = (state.hub.theaters || {})[state.plan.mapId] || {};
    const rivals = t.cortexSitsOut ? "Armada and the Null Mercs" : "Armada, Cortex and the Null Mercs";
    if (squadEl) squadEl.innerHTML = `<div class="theater-sub">The kings' showdown: your commander against ${rivals}, one commander each and nothing else. Last commander standing takes the throne. The packs and the reserve stay home.</div>`;
    renderReserve(true);
    paintDropButton();
    return;
  }
  renderReserve(dropRosterSealed());
  const squadEl = $("drop-squad");
  const kicker = $("drop-squad-kicker");
  const go = $("drop-confirm-go");
  const coreIds = crewCoreIds();
  const rented = new Set(rentedIds());
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
        tag: isCore ? "core · always" : (rented.has(e.id) ? (on ? "rented · dropping" : "rented · at base") : (on ? "dropping" : "at base")),
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
    // Bonds on this drop: rank B adds XP to both, rank A also brings the pair's gift.
    const going = new Set(livingCoreIds().concat(droppingPackIds()));
    const perks = state.hub.bondPerks || {};
    const gifts = (perks.bondGifts || []).filter(g => going.has(g.a) && going.has(g.b));
    const xps = (perks.bondXp || []).filter(r => going.has(r.a) && going.has(r.b));
    if (xps.length) html += `<div class="theater-sub spaced"><b>Bonds on this drop</b> · ${xps.map(r => {
      const g = gifts.find(x => x.a === r.a && x.b === r.b);
      return `${esc(crewHeroName(r.a))} & ${esc(crewHeroName(r.b))} (rank ${esc(r.rank)}: +${r.xp} XP each${g ? `, bringing ${g.count}× ${esc(g.name || g.unitDef)}` : ""})`;
    }).join(" · ")}</div>`;
    squadEl.innerHTML = html;
  }
  paintDropButton();
}
function paintDropButton() {
  const go = $("drop-confirm-go");
  if (go) {
    const phase = state.warm && state.warm.phase;
    go.disabled = phase === "loading" || phase === "dropping";
    go.textContent = phase === "up" ? "Back to the map"
      : phase === "dropping" ? "Dropping…"
      : phase === "loading" ? "Field loading…"
      : phase === "ready" ? "Drop"
      : phase === "failed" ? "Try again"
      : state.hostLive ? "Launch" : "Save plan";
  }
}
function pollWarm() {
  if (state.warm.poll) clearTimeout(state.warm.poll);
  const tick = async () => {
    const phase = state.warm.phase;
    if (phase !== "loading" && phase !== "ready" && phase !== "up") return;
    try {
      const status = (await api.status()).data || {};
      const hot = status.hotDrop || {};
      if (status.deployPhase === "failed" && phase === "loading") {
        const msg = String(status.error || (status.lastDeploy && status.lastDeploy.error) || "The field did not load.");
        blockDrop(msg);
        return setWarm("failed", msg);
      }
      if (phase === "loading" && hot.phase === "ready") {
        setWarm("ready");
        toast("The field is ready. Drop when your company is set.", "ok");
      } else if ((phase === "loading" || phase === "ready") && (hot.phase === "none" || hot.phase === "closed") && status.deployPhase !== "building") {
        return setWarm("idle", "Beyond All Reason closed before the drop. Launch to load the field again.");
      } else if (phase === "up" && hot.phase !== "dropped") {
        return setWarm("idle", "Beyond All Reason has closed.");
      }
    } catch (_) { /* keep waiting */ }
    state.warm.poll = setTimeout(tick, 1500);
  };
  state.warm.poll = setTimeout(tick, 1200);
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
  // Taking a door: once it is ours the extraction moves onto it (game_verdance_exfil.lua).
  const choice = ((state.hub.node || {}).choices || []).find(c => c && c.id === plan.choiceId);
  const door = choice && choice.effect && choice.effect.journey === "door" && choice.effect.door;
  const exitDoor = door && door.zoneId !== m.deployZoneId ? door.zoneId : null;
  const body = $("drop-confirm-body");
  if (body) {
    const eyes = padExposed(m.deployZoneId);
    body.innerHTML =
      `Drop on <b>${esc(prettyMap(plan.mapId))}</b> · <b>${esc(jobLabel(plan.contractKind))}</b><br>` +
      `Pad <b>${esc(zoneName(m.deployZoneId))}</b> → wound <b>${esc(targets)}</b> → ` +
      (exitDoor ? `once it is yours, leave by the door itself, <b>${esc(zoneName(exitDoor))}</b>.`
                : `back to <b>${esc(zoneName(m.deployZoneId))}</b>.`) +
      (eyes === "known" ? `<br><span class="bad">Armada has eyes on this pad.</span>` : "") +
      `<p>Get what you want onto the pad and press EXTRACT. What is off the pad stays. What stays becomes a holding.</p>`;
    body.setAttribute("data-route", body.innerHTML);
  }
  const el = $("drop-confirm");
  if (el) el.classList.add("show");
  const phase = state.warm.phase;
  if (phase === "idle" || phase === "failed") {
    // The field loads on Launch, not on opening: hire in the store first (owner call, 2026-10-27).
    resetReserveBring();
    recomputeShopAvailability();
    setWarm("idle");
    showDropTab(firstDrop() && storeWantsAttention() ? "mercs" : "party");
  } else {
    renderDropSquad();
    paintWarmStatus();
  }
}
// Launch: build the mission and start BAR now, with every pack the company could send compiled in.
async function launchField() {
  const plan = preparePlan();
  if (!plan) return;
  setWarm("loading");
  try {
    const { status, data } = await api.preload(plan);
    if (!(data && (data.accepted || data.ok))) {
      const err = (data && (data.error || data.reason)) || `The field did not load (${status})`;
      blockDrop(err);
      return setWarm("failed", err);
    }
    if (data.phase === "ready") setWarm("ready");
    logLine(`Loading ${prettyMap(plan.mapId)} behind the hub. Pick who goes.`);
    pollWarm();
  } catch (e) {
    blockDrop("Wire error: " + e.message);
    setWarm("failed", "Wire error: " + e.message);
  }
}
// Drop: the packs marked Dropping and the reserve chosen go into the loaded field.
async function dropCompany() {
  setWarm("dropping");
  try {
    const solo = soloCommand((state.plan || {}).mapId);
    const { data } = await api.drop(solo ? { crewBand: [], reserveBring: {} } : { crewBand: droppingPackIds(), reserveBring: { ...reserveBring() } });
    if (!(data && data.ok)) {
      const err = (data && data.error) || "The drop did not go through.";
      toast(err, "err");
      return setWarm("ready", err);
    }
    state.hub.flags = state.hub.flags || {};
    state.hub.flags.deployStub = false;
    state.hub.lastResult = { kind: "deploy_committed", at: new Date().toISOString() };
    renderBadges();
    logLine(`Dropped ${(data.crewBand || []).length} pack${(data.crewBand || []).length === 1 ? "" : "s"} into ${prettyMap((state.plan || {}).mapId)}.`);
    setWarm("up");
    toast("The company is down and the field is paused. Switch to Beyond All Reason and unpause when ready.", "ok");
    pollWarm();
    // The sheet has said its piece: back to the hub menu after a beat.
    setTimeout(() => { if (state.warm.phase === "up") hideDropConfirm(); }, 2000);
  } catch (e) {
    toast("Wire error: " + e.message, "err");
    setWarm("ready", "Wire error: " + e.message);
  }
}
export function onDropConfirmGo() {
  const phase = state.warm && state.warm.phase;
  if (phase === "up") return hideDropConfirm();
  if (phase === "ready") return dropCompany();
  if (phase === "loading" || phase === "dropping") return paintWarmStatus();
  if (!state.hostLive) return commitDeploy(false);
  launchField();
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
// The plan as the kernel takes it: one pad, the reserve and kit, the company as it stands.
function preparePlan() {
  const plan = state.plan;
  if (!plan) { blockDrop("Pick a sortie on the map first"); return null; }
  if (!companySealed()) { blockDrop("Form the company first — pick 3 packs and Confirm"); return null; }
  if (!(plan.marks && plan.marks.captureZoneIds && plan.marks.captureZoneIds.length)) { blockDrop("Mark a target (wound) on the map first"); return null; }
  if (!plan.marks.deployZoneId) { blockDrop("Mark a pad first"); return null; }
  plan.marks.extractZoneId = plan.marks.deployZoneId; // ONE pad
  const zones = (BOARDS[plan.mapId] || {}).zones || [];
  const dep = zones.find(z => z.zoneId === plan.marks.deployZoneId);
  if (!dep || !canLaunchFrom(plan, dep)) {
    const why = dep ? padLegality(plan.mapId, dep).why : "no such zone";
    blockDrop(`The pad must be a door we hold, ground believed ours, or the camp's next pad — ${why}`);
    return null;
  }
  const solo = soloCommand(plan.mapId);
  plan.crewBand = solo ? [] : droppingPackIds();
  plan.deployAces = solo ? [] : sealedDeployAces();
  plan.reserveBring = solo ? {} : { ...reserveBring() };
  plan.commerceDeploy = { tenebrium: commerce().tenebrium, kit: commerce().deployKit || [] };
  return plan;
}
// No kernel running (the page opened as a file): save the plan for PLAY.bat.
function commitDeploy() {
  const plan = preparePlan();
  if (!plan) return;
  try {
    downloadJson("hub_deploy_plan.json", plan);
    logLine(`Map-only plan for ${prettyMap(plan.mapId)}. Start PLAY.bat and keep its window open to fight.`);
    toast("Map only — start PLAY.bat and keep its window open to drop for real.", "err");
    state.hub.lastResult = { kind: "deploy_stub", mapId: plan.mapId, contractKind: plan.contractKind };
  } finally {
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

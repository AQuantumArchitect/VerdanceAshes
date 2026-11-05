// Operations: the drop plan, the confirm sheet, the warm (level loading) poll and the stamp.
import { state, session, BOARDS, commerce, companySealed, prettyMap, jobLabel, arcMax, deployChoicesForMap, ensureFocusMapAvailable } from "./state.js";
import { api } from "./api.js";
import { $, esc, toast, logLine, downloadJson, renderHeroCard, crewHeroName } from "./render.js";
import { defaultMarks, snapGroundRoute, isLegalLanding, padLegality, padExposed, renderBoard, renderMapPicker } from "./board.js";
import { rentedIds, renderShop, recomputeShopAvailability, renderCompany, buildCompanyEntries, crewCoreIds, droppingPackIds, sealedDeployAces, livingCoreIds, heroIsDeployable, heroAway, heroWhereLabel, companyOwnedBand, showCompanyIntro, hideCompanyIntro } from "./company.js";
import { renderBadges } from "./shell.js";
import { hideCoach } from "./system.js";
import { renderReserve, reserveBring, resetReserveBring } from "./reserve.js";
import { buildTalkQueue, renderTalks, talksLeft } from "./flow.js";

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
  toast(`${prettyMap(state.plan.mapId)}: the board shows where you land and what you take`, "ok");
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

/* ---- deploy gate: the four steps to a drop ------------------------------------------ */
// The footer shows where you are in the loop (company, job, pad, target, drop) and one button
// that names the next thing to do. The button opens the drop window (step 5), never a match.
function dropBlockReason() {
  if (!companySealed()) return "Form the company first";
  const plan = state.plan;
  if (!plan) return "Pick a job first";
  const m = plan.marks || {};
  if (!m.deployZoneId) return "Mark the pad first";
  if (!(m.captureZoneIds && m.captureZoneIds.length)) return "Mark the target first";
  return "";
}
function planZoneName(id) {
  const zones = (state.plan && (BOARDS[state.plan.mapId] || {}).zones) || [];
  const z = zones.find(x => x.zoneId === id);
  return (z && z.label) || id || "";
}
function dropSteps() {
  const plan = state.plan;
  const m = (plan && plan.marks) || {};
  const sealed = companySealed();
  const op = plan && ((session.narrative && session.narrative.operations) || []).find(o => o.id === plan.choiceId);
  const targets = (m.captureZoneIds || []).map(planZoneName).join(", ");
  const phase = state.warm && state.warm.phase !== "idle" ? state.warm.phase : "";
  const steps = [
    { key: "company", label: "Form the company", done: sealed, value: sealed ? sealedDeployAces().map(crewHeroName).join(", ") : "Pick who you are and two more" },
    { key: "job", label: "Pick a job", done: sealed && !!plan, value: op ? op.title : (plan ? `${prettyMap(plan.mapId)}: ${jobLabel(plan.contractKind)}` : "From the list on the left") },
    { key: "pad", label: "Mark the pad", done: !!m.deployZoneId, value: m.deployZoneId ? `Land and lift at ${planZoneName(m.deployZoneId)}` : "Where you land and lift (△)" },
    { key: "target", label: "Mark the target", done: !!targets, value: targets ? `Take ${targets}` : "The zone to take (◎)" },
    { key: "drop", label: "Ready the drop", done: phase === "up", value: phase === "up" ? "In the field" : (phase ? "The field is loading" : "Who goes, what they carry, mercenaries") },
  ];
  const next = steps.findIndex(st => !st.done);
  steps.forEach((st, i) => { st.state = st.done ? "done" : (i === next ? "now" : "later"); });
  return steps;
}
function renderDropSteps() {
  const el = $("drop-steps");
  if (!el) return;
  el.innerHTML = dropSteps().map((st, i) =>
    `<li class="ds-step ds-${st.state}"><button type="button" data-step="${st.key}" title="${esc(st.value)}">` +
    `<span class="ds-n">${st.done ? "✓" : i + 1}</span><span class="ds-text"><span class="ds-label">${esc(st.label)}</span>` +
    `<span class="ds-value">${esc(st.value)}</span></span></button></li>`).join("");
  el.querySelectorAll("button[data-step]").forEach(b => { b.onclick = () => goToStep(b.dataset.step); });
}
function goToStep(key) {
  if (key === "company") { if (!companySealed()) showCompanyIntro(); else document.querySelector('.cc-nav button[data-workspace="company"]')?.click(); return; }
  if (key === "job") { document.querySelector('.cc-nav button[data-workspace="operations"]')?.click(); $("operations-rail")?.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
  if (key === "pad" || key === "target") {
    const btn = document.querySelector(`.mode-btn[data-mode="${key === "pad" ? "pad" : "capture"}"]`);
    if (btn) setMarkMode(btn);
    $("board")?.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  showDropConfirm();
}
export function updateDeployGate() {
  renderDropSteps();
  const btn = $("btn-deploy");
  if (!btn) return;
  const phase = state.warm && state.warm.phase;
  btn.classList.toggle("dropping", phase === "loading" || phase === "ready" || phase === "dropping" || phase === "up");
  btn.disabled = false;
  if (phase === "up") {
    btn.title = "The company is in the field. This opens the drop window.";
    btn.textContent = "In the field";
    return;
  }
  if (phase === "loading" || phase === "ready" || phase === "dropping") {
    btn.title = "The field is loaded (or loading) behind this screen. Open the drop window to pick who goes and drop.";
    btn.textContent = phase === "loading" ? "Field loading: back to the drop" : "Field ready: back to the drop";
    return;
  }
  if (!companySealed()) {
    btn.title = "Open the company picker: choose who you are and two more, then Confirm";
    btn.textContent = "Form the company";
    return;
  }
  const block = dropBlockReason();
  btn.classList.toggle("blocked", !!block);
  if (block) {
    btn.title = block;
    btn.textContent = block.replace(/ first$/, "");
    return;
  }
  btn.title = "The field starts loading in Beyond All Reason; you talk with the company, pick who goes and what comes while it loads.";
  btn.textContent = "Choose this job";
}

/* ---- the drop sheet: the field loads while you pick who goes (hot drop) ------------ */
// Phases: idle → loading (the kernel built and started BAR; packs still open) → ready (the field
// is in, paused, nobody of ours on it) → dropping → up (the company is in). The roster locks only
// at the drop. tools/verdance_kernel/hot_drop.py has the other half.
export function dropRosterSealed() {
  const phase = state.warm && state.warm.phase;
  return phase === "dropping" || phase === "up" || !!(state.warm && state.warm.dropLocked);
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
  if (phase !== "loading" && phase !== "ready") state.warm.dropLocked = false;
  state.warm.locked = phase === "dropping" || phase === "up";
  paintWarmStatus(text);
  renderDropSquad();
  renderShop();          // the store shuts once the drop is locked
  updateDeployGate();
}
// The sortie flow's three screens, in order (owner calls, 2026-11-03/04): the camp talks, who goes,
// what comes (the reserve and the mercenary store on one screen). The green button walks them; on
// the last it drops at once, or the moment the field is ready. Every talk must be answered first.
const DROP_STEPS = ["talks", "party", "reserve"];
export function showDropTab(name) {
  if (name === "mercs") name = "reserve";
  // no skipping past the talks: they happen before the drop
  if (name !== "talks" && talksLeft() > 0) name = "talks";
  state.dropTab = DROP_STEPS.includes(name) ? name : "talks";
  if (state.dropTab === "talks") renderTalks();
  document.querySelectorAll("[data-drop-tab]").forEach(b => b.classList.toggle("on", b.dataset.dropTab === state.dropTab));
  document.querySelectorAll("[data-drop-win]").forEach(w => w.classList.toggle("on", w.dataset.dropWin === state.dropTab));
  paintDropButton();
}
function paintWarmStatus(text) {
  const el = $("drop-warm-status");
  if (!el) return;
  const phase = state.warm && state.warm.phase;
  const where = prettyMap((state.plan || {}).mapId);
  el.textContent = text || (
    phase === "loading" && state.warm.dropLocked ? `${where} is still loading. The company drops the moment it is ready.`
    : phase === "loading" ? `${where} is loading behind these screens.`
    : phase === "ready" ? "The field is ready."
    : phase === "dropping" ? "Dropping…"
    : phase === "up" ? "The company is down, the field paused. Switch to Beyond All Reason and unpause."
    : phase === "failed" ? "The field did not load. Go back to the jobs and try again."
    : ""
  );
  el.classList.toggle("ready", phase === "ready");
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
  // anyone left off is at base (owner call, 2026-11-04): no posting, no rest
  if (kicker) kicker.textContent = entries.length
    ? `${packN + coreN} on the drop · tap a card to leave someone at base`
    : `${coreIds.map(crewHeroName).join(", ")} only`;
  if (squadEl) {
    const locked = dropRosterSealed();
    const cards = entries.map(e => {
      const isCore = coreIds.includes(e.id);
      const on = e.tier === "deployed";
      const canToggle = !isCore && !!e.pickable && !locked;
      return renderHeroCard({
        id: e.id, ace: e.ace,
        tag: isCore ? "always comes" : [rented.has(e.id) ? "rented" : "", on ? "" : "at base"].filter(Boolean).join(", ") || null,
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
    // one line: how many bonds ride along and what they add; a pair with a gift is named
    if (xps.length) {
      const xpSum = xps.reduce((t, r) => t + Number(r.xp || 0), 0);
      const named = gifts.map(g => `${esc(crewHeroName(g.a))} & ${esc(crewHeroName(g.b))} bring ${g.count}× ${esc(g.name || g.unitDef)}`);
      html += `<div class="theater-sub spaced"><b>${xps.length} bond${xps.length === 1 ? "" : "s"} on this drop</b> · +${+xpSum.toFixed(2)} XP shared${named.length ? " · " + named.join(" · ") : ""}</div>`;
    }
    squadEl.innerHTML = html;
  }
  paintDropButton();
}
export function paintDropButton() {
  const go = $("drop-confirm-go");
  if (!go) return;
  const phase = state.warm && state.warm.phase;
  const tab = state.dropTab || "talks";
  go.disabled = phase === "dropping";
  go.classList.toggle("locked-drop", !!(state.warm && state.warm.dropLocked));
  const talking = tab === "talks" && talksLeft() > 0;
  if (tab === "talks") go.disabled = go.disabled || talking;
  go.textContent = phase === "up" ? "Back to the jobs"
    : phase === "dropping" ? "Dropping…"
    : tab === "talks" ? (talking ? `${talksLeft()} to answer` : "Next: who goes")
    : tab === "party" ? "Next: what comes"
    : state.warm.dropLocked ? "Drop locked: waiting for the field"
    : phase === "failed" ? "Try again"
    : !state.hostLive ? "Save plan"
    : phase === "ready" ? "Drop"
    : "Drop when ready";
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
        if (state.warm.dropLocked) return dropCompany();        // locked while it loaded: drop now
        toast("The field is ready.", "ok");
      } else if ((phase === "loading" || phase === "ready") && (hot.phase === "none" || hot.phase === "closed") && status.deployPhase !== "building") {
        return setWarm("idle", "Beyond All Reason closed before the drop. Open the drop window again to reload the field.");
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
    return toast("Form the company first: who you are, and two more", "warn");
  }
  const plan = state.plan;
  if (!plan) return toast("Mark a route on the theater first", "err");
  if (!(plan.marks && plan.marks.captureZoneIds && plan.marks.captureZoneIds.length)) return toast("Mark the target on the map first", "err");
  if (!plan.marks.deployZoneId) return toast("Mark the pad on the map first", "err");
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
    // the job in one line: where, what to take, where you lift (the rules are in "How this works")
    body.innerHTML =
      // one route line (playtest, 2026-11-04: "land and lift here · leave by there" read as two rules)
      `<b>${esc(prettyMap(plan.mapId))}</b> · take <b>${esc(targets)}</b> · land at <b>${esc(zoneName(m.deployZoneId))}</b>` +
      (exitDoor
        ? ` · lift here, or from <b>${esc(zoneName(exitDoor))}</b> once it is yours`
        : ` · lift from the same pad`) +
      (eyes === "known" ? ` · <span class="bad">Armada has eyes on this pad</span>` : "");
    body.setAttribute("data-route", body.innerHTML);
  }
  const el = $("drop-confirm");
  if (el) el.classList.add("show");
  const phase = state.warm.phase;
  if (phase === "idle" || phase === "failed") {
    // The field starts loading as the menu opens (owner call, 2026-10-28): pick heroes and hire
    // mercenaries while it loads. The drop carries the shop as it stands then, rented heroes and the
    // commander suit included: a hire never reloads the field.
    resetReserveBring();
    recomputeShopAvailability();
    setWarm("idle");
    buildTalkQueue();
    showDropTab("talks");
    if (state.hostLive) launchField();
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
  if (phase === "dropping") return paintWarmStatus();
  const tab = state.dropTab || "talks";
  if (tab === "talks" && talksLeft() > 0) return paintDropButton();
  if (tab !== "reserve") return showDropTab(DROP_STEPS[DROP_STEPS.indexOf(tab) + 1]);
  if (!state.hostLive) return commitDeploy(false);
  if (phase === "ready") return dropCompany();
  if (phase === "loading") {
    // Lock drop while the field loads: the company drops the moment it is ready. Again: unlock.
    state.warm.dropLocked = !state.warm.dropLocked;
    paintWarmStatus();
    renderDropSquad();
    renderShop();
    return;
  }
  launchField();                                  // idle or failed: (re)load, then lock
  state.warm.dropLocked = true;
  paintWarmStatus();
  paintDropButton();
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

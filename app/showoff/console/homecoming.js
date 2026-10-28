// Homecoming: the debrief card (verdict words, chips, manifest), merging a result into the
// hub, the result poll, bring-it-home and Abandon.
import { renderStory } from "./story.js";
import { state, zoneLabelAny, ensureFocusMapAvailable } from "./state.js";
import { api } from "./api.js";
import { $, esc, toast, logLine, heroNameAny } from "./render.js";
import { renderMapPicker } from "./board.js";
import { refreshTheaterForFocus } from "./operations.js";
import { renderCompany, renderShop, syncCrewFromHub, syncCompanyIntroGate } from "./company.js";
import { renderBadges, renderHeadline } from "./shell.js";
import { renderRegions } from "./system.js";

/* Ash Console copy table — keep in sync with match_credit_v1 + va_ash_tokens */
export const VERDICT_UI = {
  victory: { banner: "SECURED", headline: "Secured." },
  partial: { banner: "HINGE", headline: "Hinge — it could still go either way." },
  defeat: { banner: "FIELD COSTS", headline: "Field costs." },
  abandon: { banner: "LEFT THE FIELD", headline: "Left the field." },
  incomplete: { banner: "RESULT NOT HOME", headline: "Result not home — Retry extract or Abandon." },
};

// Debrief from the extraction manifest: who went, who stayed, where the company is now.
function renderManifest(man) {
  const box = $("hc-manifest");
  if (!box) return;
  if (!man || typeof man !== "object") { box.innerHTML = ""; box.hidden = true; return; }
  const mapId = man.mapId || null;
  const going = man.going || {};
  const staying = man.staying || {};
  const goingNames = (going.heroes || []).map(heroNameAny);
  const stayRows = (staying.heroes || []).map(h => {
    const id = typeof h === "string" ? h : (h && h.heroId);
    const zid = h && typeof h === "object" ? h.zoneId : null;
    return `${heroNameAny(id)}${zid ? ` · ${zoneLabelAny(zid, mapId)}` : ""}`;
  });
  const dest = String(man.destination || "").toLowerCase();
  const destLabel = !dest || dest === "camp" ? "Camp" : zoneLabelAny(man.destination, mapId);
  const unitsLine = (n, word) => (Number(n) > 0 ? `<li class="hm-units">${esc(n)} ${word}</li>` : "");
  const col = (title, items, extra) =>
    `<div class="hm-col"><div class="hm-h">${esc(title)}</div><ul>` +
    (items.map(s => `<li>${esc(s)}</li>`).join("") || `<li class="hm-none">nobody</li>`) + (extra || "") + `</ul></div>`;
  const kind = String(man.kind || "").toLowerCase();
  box.hidden = false;
  box.innerHTML =
    `<div class="hm-kicker">${man.pad ? `Lifted from ${esc(zoneLabelAny(man.pad, mapId))}` : "Manifest"}` +
    (kind === "wiped" ? " · nobody lifted" : kind === "closed" ? " · the field was closed" : "") + `</div>` +
    `<div class="hm-grid">` +
    col("Going", goingNames, unitsLine(going.units, "units")) +
    col("Staying", stayRows, unitsLine(staying.units, "units") + (Number(staying.structures) > 0 ? `<li class="hm-units">${esc(staying.structures)} structures → holdings</li>` : "")) +
    `<div class="hm-col"><div class="hm-h">Destination</div><ul><li>${esc(destLabel)}</li></ul></div>` +
    `</div>`;
}

export function showHomecoming(opts) {
  const el = $("homecoming");
  if (!el) return;
  const verdict = String((opts && opts.verdict) || "incomplete").toLowerCase();
  const ui = VERDICT_UI[verdict] || VERDICT_UI.incomplete;
  const banner = $("hc-banner");
  if (banner) {
    banner.textContent = (opts && opts.banner) || ui.banner;
    banner.className = "hc-banner " + verdict;
  }
  const man = (opts && opts.manifest) || null;
  const manKind = String((man && man.kind) || "").toLowerCase();
  const manHeadline = manKind === "wiped" ? "Nobody came back." : manKind === "closed" ? "Left the field." : null;
  if ($("hc-headline")) $("hc-headline").textContent = manHeadline || (opts && opts.headline) || ui.headline;
  if ($("hc-hint")) $("hc-hint").textContent = (opts && (opts.reasonHint || opts.hint)) || "";
  const chips = $("hc-chips");
  if (chips) {
    chips.innerHTML = "";
    const list = ((opts && opts.chips) || []).filter(c => !/^(collapse |H:)/.test(String(c)));
    if (man && Number(man.enemyOnPad) > 0) list.push("contested — enemies on the pad");
    list.forEach((c) => {
      if (!c) return;
      const span = document.createElement("span");
      const s = String(c);
      span.className = "hc-chip";
      if (/flip|claim|xp|secured|independents \+/i.test(s)) span.classList.add("good");
      else if (/hinge|partial|scar|no free|collapse|contested|scarcity|void/i.test(s)) span.classList.add("warn");
      else if (/defeat|wiped|lost/i.test(s)) span.classList.add("bad");
      span.textContent = s;
      chips.appendChild(span);
    });
  }
  renderManifest(man);
  el.classList.add("show");
}
export function hideHomecoming() {
  const el = $("homecoming");
  if (el) el.classList.remove("show");
}

/* ---- merging a result into the hub ------------------------------------------------- */
export function mergeHubPatch(patch) {
  if (!patch) return;
  if (patch.aces) state.hub.aces = patch.aces;
  if (patch.missionNumber != null) {
    state.hub.missionNumber = patch.missionNumber;
  }
  if (patch.reputation) state.hub.reputation = patch.reputation;
  if (patch.arc) state.hub.arc = patch.arc;
  if (patch.storyState) state.hub.storyState = patch.storyState;
  if (patch.node) state.hub.node = patch.node;
  if (patch.lastResult) state.hub.lastResult = patch.lastResult;
  // Belief frame / camp / exposure / theater rows ride along with a homecoming.
  if (patch.belief && typeof patch.belief === "object") state.hub.belief = patch.belief;
  if (patch.camp && typeof patch.camp === "object") state.hub.camp = patch.camp;
  if (patch.exposure && typeof patch.exposure === "object") state.hub.exposure = patch.exposure;
  if (patch.theater && typeof patch.theater === "object" && Array.isArray(patch.theater.zones)) state.hub.theater = patch.theater;
  // Post-sortie wallets — must update even when the poll skips a full pullHubState.
  if (patch.commerce && typeof patch.commerce === "object") state.hub.commerce = Object.assign({}, state.hub.commerce || {}, patch.commerce);
  if (patch.tenebrium != null) {
    state.hub.tenebrium = patch.tenebrium;
    state.hub.commerce = state.hub.commerce || {};
    state.hub.commerce.tenebrium = patch.tenebrium;
  }
  if (patch.factionBanks) state.hub.factionBanks = patch.factionBanks;
  if (patch.company && typeof patch.company === "object") {
    state.hub.company = Object.assign({}, state.hub.company || {}, patch.company);
    if (patch.tenebrium != null) state.hub.company.formationWalletTnb = patch.tenebrium;
    if (patch.commerce && patch.commerce.metalK != null) state.hub.company.formationWalletKm = patch.commerce.metalK;
  }
  if (patch.homeEval) state.hub.homeEval = patch.homeEval;
  if (patch.homeCamp) state.hub.homeCamp = patch.homeCamp;
  if (state.hub.flags) state.hub.flags.deployStub = false;
  const debrief = patch.debrief || (patch.lastResult && patch.lastResult.debrief) || null;
  const tokens = (patch.lastResult && patch.lastResult.tokens) || (debrief && debrief.changed) || [];
  const auto = !!(patch.autoApplied || (patch.lastResult && patch.lastResult.autoApplied));
  const headline = (debrief && debrief.headline) || patch.headline || (patch.lastResult && patch.lastResult.headline) || null;
  const verdict = (debrief && debrief.verdict) || patch.verdict || (patch.lastResult && patch.lastResult.verdict);
  const reasonHint = (debrief && debrief.reasonHint) || patch.reasonHint || (patch.lastResult && patch.lastResult.reasonHint) || "";
  // Rebuild / refresh writes verdict=state_sync — not a real homecoming.
  const isSyncNoise = !verdict || ["state_sync", "sync", "none"].includes(String(verdict).toLowerCase());
  if (!isSyncNoise && (headline || tokens.length || auto || verdict)) {
    const prefix = auto ? "Bridge: " : (verdict === "incomplete" ? "Incomplete: " : "Brought home: ");
    logLine(prefix + (headline || tokens.slice(0, 8).join(" · ") || "campaign advanced"));
    const collapseChips = (debrief && debrief.collapse && debrief.collapse.chips) || (patch.collapse && patch.collapse.chips) || [];
    const chips = [], seen = new Set();
    [...tokens, ...collapseChips].forEach((c) => {
      const s = String(c || "");
      if (!s || seen.has(s)) return;
      seen.add(s);
      chips.push(s);
    });
    showHomecoming({
      verdict: verdict || "incomplete",
      banner: (debrief && debrief.banner) || patch.banner,
      headline,
      reasonHint: reasonHint || "Review the return ledger for confirmed changes.",
      chips: chips.slice(0, 12),
      manifest: (patch.lastResult && patch.lastResult.manifest) || patch.manifest || null,
    });
    if (verdict === "incomplete") toast(headline || "Result not home — retry bring-home or Abandon", "err");
    else if (verdict === "abandon") toast(headline || "Left the field — mark the next board", "warn");
    else if (debrief && debrief.duplicate) toast("Already applied — state unchanged", "ok");
    else toast(auto ? (headline || "Bridge brought the sortie home") : (headline || "The ashes keep score — company and map updated"), "ok");
  } else if (isSyncNoise && tokens.length) {
    logLine("Map synced · " + tokens.slice(0, 6).join(" · "));
  }
  renderBadges();
  renderCompany();
  renderRegions();
  renderShop();
  renderHeadline();
  renderMapPicker();
  renderStory();
}

export async function pullHubState() {
  if (!state.hostLive) return;
  const { data: j } = await api.hubState();
  if (!(j.ok && j.hub)) return;
  const focus = state.focusMap;
  state.hub = j.hub;
  state.focusMap = focus || j.hub.sessionHomeMap || (j.hub.node && j.hub.node.regionHint);
  ensureFocusMapAvailable();
  if (state.hub.flags) state.hub.flags.deployStub = false;
  syncCrewFromHub();
  renderBadges();
  renderCompany();
  renderRegions();
  renderShop();
  renderHeadline();
  renderStory();
  refreshTheaterForFocus();
  syncCompanyIntroGate(); // re-open the formation picker if a refresh left us unsealed without it
  logLine("Map refreshed from the living campaign");
}

export async function pullBarResult() {
  if (!state.hostLive) return toast("Start PLAY.bat and keep its window open", "err");
  toast("Listening for the last sortie…");
  try {
    const { data: j } = await api.advanceExtract();
    const { data: rj } = await api.result();
    if (rj.present && rj.result) {
      state.lastResultAt = rj.result.at;
      mergeHubPatch({ ...rj.result, debrief: j.debrief || rj.result.debrief, headline: j.headline || rj.result.headline, verdict: j.verdict || rj.result.verdict });
    } else if (j.debrief || (j.apply && j.apply.lastResult) || j.incomplete) {
      mergeHubPatch({
        lastResult: (j.apply && j.apply.lastResult) || j.lastResult,
        debrief: j.debrief, headline: j.headline, verdict: j.verdict,
        missionNumber: j.apply && j.apply.missionNumber,
        tenebrium: j.tenebrium || (j.apply && j.apply.tenebrium),
        commerce: j.commerce || (j.apply && j.apply.commerce),
        company: j.company || (j.apply && j.apply.company),
        factionBanks: j.factionBanks || (j.apply && j.apply.factionBanks),
      });
    } else if (!j.ok) {
      toast((j.error || (j.apply && j.apply.error) || "Nothing to bring home yet — finish a match or Abandon"), "err");
      return;
    }
    await pullHubState(); // always re-pull hub SoT so Tnb / km$ badges match campaign_state
    if (!(rj.present && rj.result) && !(j.debrief || (j.apply && j.apply.lastResult) || j.incomplete)) toast("Map refreshed — no new scars this pass", "ok");
  } catch (e) {
    toast("Could not bring it home: " + e.message, "err");
  }
}

export async function abandonSortie() {
  if (!state.hostLive) return toast("Start PLAY.bat and keep its window open", "err");
  if (!confirm("Abandon this sortie? No zone flip, no fake win. Next Drop unlocks.")) return;
  try {
    const { data: j } = await api.abandon();
    if (j.ok || j.abandon) {
      mergeHubPatch({ debrief: j.debrief, headline: j.headline || "Left the field.", verdict: "abandon", lastResult: { verdict: "abandon", debrief: j.debrief, at: j.at } });
      await pullHubState();
    } else {
      toast(j.error || "Abandon failed", "err");
    }
  } catch (e) {
    toast("Abandon failed: " + e.message, "err");
  }
}

// The bridge may auto-apply a result; poll /api/result and bring new ones home.
export function startResultPoll() {
  if (startResultPoll._on) return;
  startResultPoll._on = true;
  setInterval(async () => {
    if (!state.hostLive) return;
    try {
      const { data: rj } = await api.result();
      if (rj.present && rj.result && rj.result.at && rj.result.at !== state.lastResultAt) {
        state.lastResultAt = rj.result.at;
        mergeHubPatch({ ...rj.result, autoApplied: !!(rj.result.autoApplied), lastResult: rj.result.lastResult || rj.result });
        await pullHubState(); // full hub pull so Tnb/km$ cannot lag behind the debrief card
      }
    } catch (_) { /* host down */ }
  }, 2000); // the kernel brings the result home during BAR's closing countdown; be ready first
}

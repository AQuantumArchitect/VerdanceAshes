// The company: formation (intro picker + seal), who drops vs who stays, the recruit
// tease, standing, and the broker (shelves + bag).
import { state, CREW, list, companySurface, companySealed, commerce, metalKOf, prettyMapShort, repLabel, zoneLabelAny } from "./state.js";
import { api } from "./api.js";
import { $, esc, toast, logLine, downloadJson, renderHeroCard, crewPack, crewHeroName, aceById, heroNameAny } from "./render.js";
import { wildRecruitAtZone, renderBoard } from "./board.js";
import { updateDeployGate, noteRosterChanged, dropRosterSealed, refreshTheaterForFocus } from "./operations.js";
import { renderBadges, renderHeadline } from "./shell.js";
import { showCoach } from "./system.js";
import { pullHubState } from "./homecoming.js";

/* ---- wallet + catalogue ---------------------------------------------------------- */
export function crewSeatCap() {
  const c = companySurface();
  return Number(c.seatCap) || Number(CREW.seatCap) || 3;
}
export function crewWallet() {
  // Prefer the live commerce bag (post-sortie SoT); formationWallet* mirrors it on hub
  // rebuild; never let a falsy 0 fall through to startWalletTnb.
  const bag = (state.hub && state.hub.commerce) || {};
  if (bag.tenebrium != null && bag.tenebrium !== "") return Number(bag.tenebrium) || 0;
  const c = companySurface();
  if (c.formationWalletTnb != null && c.formationWalletTnb !== "") return Number(c.formationWalletTnb) || 0;
  return Number(CREW.startWalletTnb) || 3;
}
export function crewMetalK() {
  const bag = (state.hub && state.hub.commerce) || {};
  if (bag.metalK != null && bag.metalK !== "") return Number(bag.metalK) || 0;
  const c = companySurface();
  if (c.formationWalletKm != null && c.formationWalletKm !== "") return Number(c.formationWalletKm) || 0;
  return Number(CREW.startWalletKm) || 0;
}
export function crewHireCost(id) {
  const h = (CREW.heroes || {})[id];
  return h ? Number(h.hireTnb) || 0 : 99;
}
function crewHireKm(id) {
  const h = (CREW.heroes || {})[id];
  return h ? Number(h.hireKm) || 0 : 0;
}
function crewSpent() { return state.crewBand.reduce((n, id) => n + crewHireCost(id), 0); }
export function crewCoreIds() {
  const c = companySurface();
  if (Array.isArray(c.core) && c.core.length) return c.core.map(x => (typeof x === "string" ? x : x.id)).filter(Boolean);
  return Array.isArray(CREW.core) ? CREW.core.slice() : ["vane", "ketha"];
}
export function crewBandOrder() {
  const c = companySurface();
  let ids;
  if (Array.isArray(c.unlockedIds) && c.unlockedIds.length) ids = c.unlockedIds.slice();
  else if (Array.isArray(c.pool) && c.pool.length) ids = c.pool.map(p => p.id);
  else ids = Object.keys(CREW.heroes || {}).filter(id => CREW.heroes[id] && CREW.heroes[id].role === "band");
  return sortHeroGridIds(ids);
}
function heroIsEco(id) {
  const h = crewPack(id);
  const tags = h.tags || [];
  const fe = String(h.fieldEffect || "");
  if (fe === "energy" || fe === "build") return true;
  if (tags.includes("eco_lab") || tags.includes("pad_heart") || tags.includes("field_office") || tags.includes("combat_engineer")) return true;
  return id === "hearth" || id === "solarium" || id === "consul" || id === "twitch";
}
function sortHeroGridIds(ids) {
  // Eco cluster first, then startXp (premium/green first), then pack cost.
  const catalogRank = Object.fromEntries((Array.isArray(CREW.bandOrder) ? CREW.bandOrder : []).map((id, i) => [id, i]));
  return (ids || []).slice().sort((a, b) => {
    const ae = heroIsEco(a) ? 0 : 1, be = heroIsEco(b) ? 0 : 1;
    if (ae !== be) return ae - be;
    const ha = crewPack(a), hb = crewPack(b);
    const ax = Number(ha.startXp), bx = Number(hb.startXp);
    const axn = Number.isFinite(ax) ? ax : 0.5, bxn = Number.isFinite(bx) ? bx : 0.5;
    if (axn !== bxn) return axn - bxn;
    const ac = Number(ha.packCombined) || 0, bc = Number(hb.packCombined) || 0;
    if (ac !== bc) return ac - bc;
    const ar = catalogRank[a], br = catalogRank[b];
    if (ar != null && br != null && ar !== br) return ar - br;
    return String(a).localeCompare(String(b));
  });
}
export function companyOwnedBand() {
  const c = companySurface();
  return list(c.band).concat(list(c.joinedLater));
}

/* ---- where people are --------------------------------------------------------------- */
function heroAwayRec(id) {
  const camp = (state.hub && state.hub.camp) || {};
  const people = Array.isArray(camp.people) ? camp.people : [];
  return people.find(p => p && (p.heroId === id || p.hid === id)) || null;
}
export function heroAway(id) {
  const ace = aceById(id);
  const rec = heroAwayRec(id);
  const where = String((rec && rec.where) || (ace && ace.where) || "camp").toLowerCase();
  return where === "posted" || where === "transit" || where === "field";
}
export function heroWhereLabel(id) {
  // "posted · Northwest Bastion" / "in the field · Central Gate" / "on the road"
  const ace = aceById(id);
  const rec = heroAwayRec(id);
  const where = String((rec && rec.where) || (ace && ace.where) || "camp").toLowerCase();
  const place = rec && (rec.label || rec.zoneId);
  const word = ({ posted: "posted", transit: "on the road", field: "in the field" })[where] || where;
  return place ? `${word} · ${place}` : word;
}
export function heroIsDeployable(id) {
  // Dead / lost stay on the company roll but do not drop; people posted, on the road or
  // left in the field are not at camp and cannot board until they come home.
  const ace = aceById(id);
  const st = String((ace && ace.status) || "active").toLowerCase();
  if (st === "dead" || st === "lost") return false;
  if (ace && ace.deployable === false) return false;
  return !heroAway(id);
}
export function livingCoreIds() { return crewCoreIds().filter(heroIsDeployable); }
export function droppingPackIds() {
  // Packs on this Drop. Before the first hub sync, assume the whole company so a fast
  // click cannot ship core-only by accident.
  const core = new Set(crewCoreIds());
  if (companySealed() && !state.sortieSynced) return companyOwnedBand().filter(id => !core.has(id) && heroIsDeployable(id));
  return state.crewBand.filter(id => !core.has(id) && heroIsDeployable(id));
}
export function sealedDeployAces() { return livingCoreIds().concat(droppingPackIds()); }
export function companyMemberIds() {
  return [...new Set([...crewCoreIds(), ...(companySealed() ? companyOwnedBand() : state.crewBand)])];
}
// People of ours not at camp, with where they are: for the operations rail.
export function fieldPeople() {
  const camp = (state.hub && state.hub.camp) || {};
  return (Array.isArray(camp.people) ? camp.people : [])
    .filter(p => p && ["posted", "transit", "field"].includes(String(p.where || "").toLowerCase()))
    .map(p => ({ heroId: p.heroId, name: p.name || heroNameAny(p.heroId), where: p.where, label: p.label || zoneLabelAny(p.zoneId, p.mapId), wounded: !!p.wounded }));
}

export function syncCrewFromHub() {
  const c = companySurface();
  if (!c.sealed) return;
  const ownedList = companyOwnedBand().filter(heroIsDeployable);
  const owned = new Set(ownedList);
  // Server Drop stamps company.deployBand (formation band + joinedLater). Prefer that on
  // first paint so The Company matches what BAR actually receives.
  const serverBand = list(c.deployBand).filter(id => owned.has(id) && heroIsDeployable(id));
  if (!state.knownCompanyIds) state.knownCompanyIds = new Set();
  if (!state.sortieSynced) {
    state.crewBand = (serverBand.length ? serverBand : ownedList).slice();
    state.knownCompanyIds = new Set(ownedList);
    state.sortieSynced = true;
    return;
  }
  // Keep local Dropping↔Base picks for people already sorted; absorb brand-new members
  // (field rescues) into Dropping so the Drop ships them.
  state.crewBand = state.crewBand.filter(id => owned.has(id) && heroIsDeployable(id));
  for (const id of ownedList) {
    if (!state.knownCompanyIds.has(id)) {
      if (!state.crewBand.includes(id)) state.crewBand.push(id);
      state.knownCompanyIds.add(id);
    }
  }
  for (const id of [...state.knownCompanyIds]) if (!owned.has(id)) state.knownCompanyIds.delete(id);
}

/* ---- picking ------------------------------------------------------------------------- */
export function toggleCrew(id) {
  if (dropRosterSealed()) return toast("This company is locked for the drop. Close Recoil to change who ships.", "warn");
  if (crewCoreIds().includes(id)) {
    if (!heroIsDeployable(id)) return toast(`${crewHeroName(id)} is fallen — they are not dropping`, "warn");
    return toast(
      `${crewHeroName(id)} is core — always drops, and does not use a pack seat. ` +
      (companySealed() ? "You can bring every other living pack, or click one to leave it at base." : `Pick exactly ${crewSeatCap()} other packs.`),
      "ok"
    );
  }
  const owned = new Set(companyOwnedBand());
  const i = state.crewBand.indexOf(id);
  if (companySealed()) {
    // Post-seal: move between Dropping ↔ At base (company members only).
    if (!owned.has(id)) return toast("Still locked — find them in the field", "err");
    if (!heroIsDeployable(id)) {
      if (i >= 0) state.crewBand.splice(i, 1);
      if (state.plan) state.plan.deployAces = sealedDeployAces();
      renderCompany();
      renderBoard();
      if (heroAway(id)) return toast(`${crewHeroName(id)} is ${heroWhereLabel(id)} — not at camp, so not boarding`, "warn");
      return toast(`${crewHeroName(id)} is fallen — that's why they're not here`, "warn");
    }
    if (i >= 0) {
      state.crewBand.splice(i, 1);
      toast(`${crewHeroName(id)} stays at base`, "ok");
    } else {
      state.crewBand.push(id);
      toast(`${crewHeroName(id)} joins the sortie`, "ok");
    }
    if (state.plan) state.plan.deployAces = sealedDeployAces();
    renderCompany();
    renderBoard();
    noteRosterChanged();
    return;
  }
  // Preamble formation: the first pick is you (state.crewYou; must walk), then companions.
  if (state.crewYou === id) state.crewYou = null;
  else if (i >= 0) state.crewBand.splice(i, 1);
  else if (state.crewBand.length + (state.crewYou ? 1 : 0) >= crewSeatCap()) return toast(`Pick exactly ${crewSeatCap()}: yourself and ${crewSeatCap() - 1} others`, "err");
  else if (formationSpent() + crewHireCost(id) > crewWallet()) return toast("Not enough formation Tnb for that build-power seat", "err");
  else if (!state.crewYou && heroCanLead(id)) state.crewYou = id;
  else if (state.crewBand.length >= crewSeatCap() - 1) return toast(`${crewHeroName(id)} cannot lead; pick who you are first`, "err");
  else state.crewBand.push(id);
  renderCompany();
  renderCompanyIntro();
}

/* Heroes not yet unlocked: rescue one in the field and bring them through a campaign alive. */
function lockedHeroIds(pool) {
  const open = new Set(pool.concat(crewCoreIds()));
  return Object.keys(CREW.heroes || {}).filter(id => CREW.heroes[id]?.role === "band" && !open.has(id));
}

/* The first pick is you: the hero the player is. Buildings cannot lead. */
export function heroCanLead(id) { return crewPack(id).canLead !== false; }
function formationPicks() { return (state.crewYou ? [state.crewYou] : []).concat(state.crewBand); }
function formationSpent() { return formationPicks().reduce((n, id) => n + crewHireCost(id), 0); }

export function recommendCompany() {
  if (companySealed()) return;
  // You are Pavise; Solarium and Halbard come with you. The real choice it sets up:
  // swap Halbard for Vane (stronger, worse against the early beamer fights).
  const pool = new Set(crewBandOrder());
  const pick = ["pavise", "solarium", "halbard"].filter(id => pool.has(id) && !["dead", "lost"].includes(String(aceById(id)?.status || "active")));
  if (pick.length !== crewSeatCap() || pick.reduce((n, id) => n + crewHireCost(id), 0) > crewWallet()) {
    return toast("The recommended company is not available. Choose individually.", "warn");
  }
  state.crewYou = pick[0];
  state.crewBand = pick.slice(1);
  renderCompany();
  renderCompanyIntro();
  toast("You are Pavise, with Solarium and Halbard. Swap Halbard for Vane if you want more punch.", "ok");
}

/* ---- company intro (first run) ------------------------------------------------------- */
export function showCompanyIntro() {
  const el = $("company-intro");
  if (!el) return;
  el.classList.add("show");
  try { renderCompanyIntro(); }
  catch (err) {
    console.error("company intro render failed", err);
    toast("Company picker hit a snag — try Refresh", "err");
  }
}
export function hideCompanyIntro() {
  const el = $("company-intro");
  if (el) el.classList.remove("show");
}
export function syncCompanyIntroGate() {
  if (companySealed()) { hideCompanyIntro(); return false; }
  showCompanyIntro();
  return true;
}
function renderCompanyIntro() {
  const grid = $("company-intro-grid");
  const slotsEl = $("company-intro-slots");
  const metaEl = $("company-intro-meta");
  const countEl = $("company-intro-count");
  const sealBtn = $("btn-seal-company-intro");
  if (!grid) return;
  if (companySealed()) { hideCompanyIntro(); return; }
  const cap = crewSeatCap();
  const coreIds = crewCoreIds();
  const picks = formationPicks();
  const pool = crewBandOrder().filter(id => !coreIds.includes(id));
  if (metaEl) {
    const spent = formationSpent(), wallet = crewWallet();
    metaEl.innerHTML =
      `<span class="chip">${coreIds.map(crewHeroName).join(", ")} always comes</span>` +
      `<span class="chip">${picks.length}/${cap} chosen</span>` +
      (spent > 0 ? `<span class="chip">${wallet - spent}/${wallet} Tnb left (builders)</span>` : `<span class="chip">Combat seats free</span>`);
  }
  // Slots: you (void-touched, top), then the companions.
  if (slotsEl) {
    const youCard = state.crewYou
      ? renderHeroCard({ id: state.crewYou, tag: "you", classes: ["on", "toggleable"], panel: true, compact: true, hideCost: true, dataCrew: state.crewYou, type: "button" })
      : `<div class="slot-empty">Choose who you are. Anyone who can walk.</div>`;
    const companions = [];
    for (let k = 0; k < cap - 1; k++) {
      const id = state.crewBand[k];
      companions.push(id
        ? renderHeroCard({ id, classes: ["on", "toggleable"], panel: true, compact: true, hideCost: true, dataCrew: id, type: "button" })
        : `<div class="slot-empty">Companion</div>`);
    }
    slotsEl.innerHTML =
      `<div class="slot-you"><div class="slot-label">You · void-touched</div>${youCard}</div>` +
      `<div class="slot-companions"><div class="slot-label">Who comes with you</div><div class="slot-row">${companions.join("")}</div></div>`;
  }
  const full = picks.length >= cap;
  const needYou = !state.crewYou;
  grid.innerHTML = pool.filter(id => !picks.includes(id)).map(id => {
    const cost = crewHireCost(id), costKm = crewHireKm(id);
    const broke = formationSpent() + cost > crewWallet();
    // While "you" is open and only one seat is left, a building cannot take it.
    const noLead = needYou && !heroCanLead(id) && state.crewBand.length >= cap - 1;
    const locked = full || broke || noLead;
    return renderHeroCard({
      id,
      tag: heroCanLead(id) ? null : "cannot lead",
      classes: [locked ? "locked" : "toggleable"].filter(Boolean),
      costTnb: cost, costKm, pickable: true, showFreeCost: true, panel: true, compact: true,
      dataCrew: locked ? null : id, disabled: locked, type: "button",
    });
  }).join("") + lockedHeroIds(pool).map(id => renderHeroCard({
    id, tag: "rescue to unlock", classes: ["locked", "rescue-locked"], panel: true, compact: true, hideCost: true, disabled: true,
  })).join("");
  if (countEl) {
    countEl.innerHTML = picks.length === cap
      ? `Ready · <b>${crewHeroName(state.crewYou)}</b> (you) · ${state.crewBand.map(crewHeroName).join(" · ")} · ${coreIds.map(crewHeroName).join(" · ")}`
      : (needYou ? "Choose who you are" : `Pick <b>${cap - picks.length}</b> more`);
  }
  if (sealBtn) {
    sealBtn.disabled = picks.length !== cap || needYou;
    sealBtn.textContent = picks.length === cap ? "Confirm company" : `Confirm (${picks.length}/${cap})`;
  }
}

export async function sealCompany() {
  if (companySealed()) return toast("Company already sealed", "ok");
  if (!state.crewYou || formationPicks().length !== crewSeatCap()) return toast("Choose who you are, then " + (crewSeatCap() - 1) + " others", "err");
  if (!state.hostLive) return toast("Start PLAY.bat and keep its window open to seal the company", "err");
  try {
    toast("Sealing company…");
    const { ok, data: j } = await api.sealCompany(formationPicks());
    if (!ok || j.ok === false) return toast((j && j.error) || "Seal failed", "err");
    if (j.hub) state.hub = j.hub;
    else await pullHubState();
    // Formation picks become the first sortie roster; the rest of the catalogue stays locked.
    state.sortieSynced = true;
    state.crewYou = null;
    syncCrewFromHub();
    hideCompanyIntro();
    renderCompany();
    renderHeadline();
    refreshTheaterForFocus();
    logLine("Company sealed — " + sealedDeployAces().map(crewHeroName).join(", "));
    toast("Company sealed — only your run roster is on the board.", "ok");
    showCoach(false); // after first seal, show the how-to coach once
  } catch (e) {
    toast("Seal failed: " + e.message, "err");
  }
}

/* ---- roster entries (drop confirm) -------------------------------------------------------- */
function companyStatusRank(entry) {
  return ({ deployed: 0, base: 1, away: 2, dead: 3, locked: 4 })[entry.tier || "locked"] ?? 9;
}
export function buildCompanyEntries() {
  const sealed = companySealed();
  const coreIds = crewCoreIds();
  const deployIds = new Set(sealedDeployAces());
  const ownedBand = companyOwnedBand();
  const laterIds = new Set(list(companySurface().joinedLater));
  const aces = (state.hub.aces || []).slice();
  const aceMap = Object.fromEntries(aces.map(a => [a.id, a]));
  const seen = new Set();
  const entries = [];
  function push(id, tier, extra) {
    if (!id || seen.has(id)) return;
    seen.add(id);
    const ace = aceMap[id] || null;
    const st = String((ace && ace.status) || (extra && extra.status) || "").toLowerCase();
    entries.push(Object.assign({
      id, tier: (st === "dead" || st === "lost") ? "dead" : tier, ace, pack: crewPack(id),
      name: (extra && extra.name) || (ace && ace.name) || crewHeroName(id),
    }, extra || {}));
  }
  if (!sealed) {
    coreIds.forEach(id => push(id, "deployed", { tag: "core", pickable: false }));
    state.crewBand.forEach(id => push(id, "deployed", { tag: "picked", pickable: true, on: true }));
  } else {
    // Sealed: only this-run company. Dropping ↔ At base. Never dump unlocks.
    deployIds.forEach(id => push(id, "deployed", { tag: coreIds.includes(id) ? "core · always" : (laterIds.has(id) ? "field join" : null), pickable: true, on: true }));
    ownedBand.forEach(id => {
      if (deployIds.has(id)) return;
      const st = String((aceMap[id] && aceMap[id].status) || "active").toLowerCase();
      if (st === "dead" || st === "lost") return push(id, "dead", { pickable: false });
      if (heroAway(id)) return push(id, "away", { tag: heroWhereLabel(id), pickable: false, on: false });
      push(id, "base", { tag: laterIds.has(id) ? "field join" : "at base", pickable: true, on: false });
    });
    coreIds.forEach(id => { if (!seen.has(id) && heroAway(id)) push(id, "away", { tag: "core · " + heroWhereLabel(id), pickable: false, on: false }); });
    aces.forEach(a => {
      if (!a || !a.id || seen.has(a.id)) return;
      const st = String(a.status || "").toLowerCase();
      if (st === "dead" || st === "lost") push(a.id, "dead", { pickable: false });
    });
  }
  entries.sort((a, b) => {
    const d = companyStatusRank(a) - companyStatusRank(b);
    if (d !== 0) return d;
    const ac = coreIds.includes(a.id) ? 0 : 1, bc = coreIds.includes(b.id) ? 0 : 1;
    if (ac !== bc) return ac - bc;
    return String(a.name || a.id).localeCompare(String(b.name || b.id));
  });
  return entries;
}

/* ---- the Company workspace ----------------------------------------------------------- */
function renderCompanyRecruitSlot() {
  const wrap = $("company-recruit");
  const cardEl = $("company-recruit-card");
  const kicker = $("company-recruit-kicker");
  if (!wrap || !cardEl) return;
  const mapId = (state.plan && state.plan.mapId) || state.focusMap;
  const zoneId = state.selectedZoneId || ((state.plan && state.plan.marks && (state.plan.marks.captureZoneIds || [])[0]) || null);
  const hit = wildRecruitAtZone(mapId, zoneId);
  if (!hit) {
    wrap.hidden = true;
    cardEl.innerHTML = "";
    return;
  }
  const h = crewPack(hit.id);
  const how = ((hit.recruit && hit.recruit.type) || "wreck_rez").replace(/_/g, " ");
  if (kicker) kicker.textContent = `Belief collapse · ${how} · wreck`;
  cardEl.innerHTML = renderHeroCard({
    id: hit.id, name: hit.name || crewHeroName(hit.id), classes: ["tier-locked", "wild"],
    meta: `${prettyMapShort(hit.mapId || mapId)} · ${hit.zoneId || zoneId || "zone"}`,
    blurb: (hit.recruit && hit.recruit.blurb) || h.blurb || "Their wreck is on this pad — rez them to join. No live poof.",
    panel: true, disabled: true,
  });
  wrap.hidden = false;
}
export function renderCompany() {
  const sealed = companySealed();
  const cap = crewSeatCap();
  const col = $("col-aces");
  const theater = $("theater");
  if (col) col.classList.toggle("company-preamble", !sealed);
  if (theater) theater.classList.toggle("company-locked", !sealed);
  // Intro modal owns formation; keep it in sync (or closed once sealed). Never silently
  // leave the picker hidden while the company is unsealed — the Drop loop looks broken.
  if (sealed) hideCompanyIntro();
  else { try { renderCompanyIntro(); } catch (err) { console.error(err); } }

  const walletEl = $("company-wallet");
  if (walletEl) {
    if (sealed) {
      const later = list(companySurface().joinedLater);
      const bag = `${crewWallet()} Tnb · ${(crewMetalK() * 1000).toLocaleString()} metal`;
      walletEl.textContent = later.length ? `Sealed · ${bag} · +${later.length} join${later.length === 1 ? "" : "s"}` : `Sealed · ${bag}`;
    } else {
      const spentTnb = crewSpent(), wallet = crewWallet();
      walletEl.textContent = spentTnb > 0
        ? `${wallet - spentTnb}/${wallet} Tnb (builders/reactors) · ${state.crewBand.length}/${cap}`
        : `Combat seats free · ${state.crewBand.length}/${cap}`;
    }
  }
  renderCompanyRecruitSlot();
  const rep = state.hub.reputation || {};
  if ($("rep")) {
    $("rep").innerHTML = Object.entries(rep).map(([k, v]) =>
      `<div class="panel-card"><div class="row"><span class="rep-name">${esc(repLabel(k))}</span><strong>${esc(v)}</strong></div></div>`
    ).join("");
  }
  updateDeployGate();
}

/* ---- broker ------------------------------------------------------------------------- */
function shopShelfOf(item) {
  const raw = String(item.shelf || "").toLowerCase();
  if (raw) return raw;
  const tags = (item.tags || []).map(t => String(t).toLowerCase());
  if (tags.includes("armada")) return "armada";
  if (tags.includes("nullmercs") || tags.includes("null")) return "nullmercs";
  if (tags.includes("cortex")) return "cortex";
  if (item.kind === "hero_contract") return "nullmercs";
  return "cortex";
}
function shopShelfLabel(id) {
  return ({ cortex: "Cortex · arms merchant", armada: "Armada · surplus", nullmercs: "Null Mercs", camp: "Camp" })[id] || id;
}
function renderShopListing(item) {
  const locked = !item.available;
  const owned = item.owned;
  const purchaseStack = item.kind === "purchase_package";
  const costs = [];
  if (item.tenebriumCost) costs.push(`${item.tenebriumCost} Tnb`);
  const mkCost = Number(item.metalCostK != null ? item.metalCostK : item.creditCost || 0);
  if (mkCost) costs.push(`${(mkCost * 1000).toLocaleString()} metal`);
  if (!costs.length) costs.push("—");
  const d = item.delivery || {};
  const etaLine = d.summary || d.etaText ? `<div class="cost">${esc(d.summary || d.etaText)}</div>` : "";
  const ownedLine = owned
    ? (purchaseStack ? `<div class="block good">Owned ×${esc(item.ownedQty || 1)} — buy again to stack</div>` : `<div class="block good">In bag / installed</div>`)
    : "";
  const showBuy = purchaseStack || !owned;
  const tags = (item.tags || []).filter(t => !String(t).toLowerCase().startsWith("role:"));
  return `<div class="listing ${owned ? "owned" : ""} ${locked ? "locked" : ""}" data-id="${esc(item.id)}">
      <div class="title"><strong>${esc(item.label)}</strong><span class="cost">${esc(costs.join(" · "))}</span></div>
      <div class="blurb">${esc(item.blurb)}</div>
      <details><summary>Pack details</summary><div class="cost">${esc(item.kind.replaceAll("_", " "))}${item.unitDef ? " · " + esc(item.unitDef) : ""}${item.count ? " ×" + esc(item.count) : ""}${item.builds ? " · construction equipment" : ""}</div></details>
      ${etaLine}
      ${locked ? `<div class="block">${esc(item.blockedReason || "locked")}</div>` : ""}
      ${ownedLine}
      <div class="tags">${tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>
      ${showBuy ? `<button type="button" class="btn-buy" data-buy="${esc(item.id)}" ${locked ? "disabled" : ""}>${state.hostLive ? (purchaseStack && owned ? "Buy another" : "Buy") : "Preview buy"}</button>` : ""}
    </div>`;
}
export function renderShop() {
  const c = commerce();
  $("shop-balances").innerHTML = `
      <div class="bal tnb">Tenebrium<strong>${c.tenebrium ?? 0}</strong>∞ storage</div>
      <div class="bal cred">Metal<strong>${(metalKOf(c) * 1000).toLocaleString()} metal</strong>~${metalKOf(c) * 1000} banked</div>`;
  $("shop-note").textContent = state.hostLive
    ? "Each purchase shows its cost and delivery time. Construction equipment can require Tenebrium as well as metal."
    : "Preview only. Start PLAY.bat and keep its window open to make campaign purchases.";
  const kit = c.deployKit || [];
  const inbound = c.inbound || c.pendingDeliveries || [];
  const kitHtml = kit.map(k => `<div class="kit-line"><b>${esc(k.label || k.listingId)}</b>${k.count ? " · ×" + esc(k.count) : ""}${k.loan ? " · loan" : ""}${k.factoryDef ? " · fabricator" : ""}</div>`).join("");
  const inboundHtml = inbound.map(k => {
    const d = k.delivery || {};
    return `<div class="kit-line"><b>INBOUND</b> ${esc(k.label || k.listingId)}${k.count ? " · ×" + esc(k.count) : ""}${d.etaText ? " · " + esc(d.etaText) : ""}${d.sourceLabel ? " · from " + esc(d.sourceLabel) : ""}${d.summary ? `<div class="meta">${esc(d.summary)}</div>` : ""}</div>`;
  }).join("");
  $("deploy-kit").innerHTML = (kitHtml || inboundHtml) ? (kitHtml + inboundHtml) : `<div class="kit-line">Empty bag — buy a Punch, stream, or fab before you Drop.</div>`;
  const order = ["nullmercs", "cortex", "armada", "camp"];
  const groups = {};
  (c.shop || []).forEach(item => { const shelf = shopShelfOf(item); (groups[shelf] || (groups[shelf] = [])).push(item); });
  const shelfIds = order.filter(id => groups[id] && groups[id].length).concat(Object.keys(groups).filter(id => !order.includes(id)));
  $("shop-list").innerHTML = shelfIds.map(shelf => `<div class="shop-shelf">${esc(shopShelfLabel(shelf))}</div>${groups[shelf].map(renderShopListing).join("")}`).join("")
    || `<div class="panel-card meta">Broker is empty — re-export the campaign pack.</div>`;
}
export function recomputeShopAvailability() {
  const c = commerce();
  const rep = state.hub.reputation || {};
  const mission = state.hub.missionNumber || 1;
  const arcN = mission <= 5 ? 1 : mission <= 10 ? 2 : 3;
  const owned = c.owned || {};
  const upgrades = c.upgrades || {};
  (c.shop || []).forEach(item => {
    let ok = true, reason = null;
    const kind = item.kind || "";
    if (kind === "printer_upgrade" && upgrades[item.id]) { ok = false; reason = "upgrade already installed"; }
    if ((kind === "unit_printer" || kind === "loan_package") && owned[item.id]) { ok = false; reason = "already owned"; }
    if (item.starterOwned && item.loan && owned[item.id]) { ok = false; reason = "already owned (starter loan)"; }
    if (item.requires && !owned[item.requires]) { ok = false; reason = "requires " + item.requires; }
    if ((item.arcMin || 1) > arcN) { ok = false; reason = "arc " + item.arcMin + "+ only"; }
    const repMin = item.repMin || {};
    for (const f of Object.keys(repMin)) {
      if (Number(rep[f] || 0) < Number(repMin[f])) { ok = false; reason = `need ${f} rep ≥ ${repMin[f]}`; }
    }
    const tcost = Number(item.tenebriumCost || 0);
    const mcost = Number(item.metalCostK != null ? item.metalCostK : item.creditCost || 0);
    if (Number(c.tenebrium || 0) < tcost) { ok = false; reason = `need ${tcost} Tenebrium`; }
    if (metalKOf(c) < mcost) { ok = false; reason = `need ${(mcost * 1000).toLocaleString()} metal`; }
    item.available = ok;
    item.blockedReason = ok ? null : reason;
    item.owned = !!(owned[item.id] || upgrades[item.id]);
  });
  // rebuild deploy kit labels lightly
  const kit = [];
  for (const [lid, rec] of Object.entries(owned)) {
    if (!rec || typeof rec !== "object") continue;
    const listing = (c.shop || []).find(s => s.id === lid) || {};
    kit.push({ listingId: lid, kind: rec.kind || listing.kind, unitDef: rec.unitDef || listing.unitDef, count: rec.loanCount || rec.count || listing.count, loan: !!(rec.loan || listing.loan), label: listing.label || lid, factoryDef: rec.factoryDef, product: rec.product });
  }
  for (const uid of Object.keys(upgrades)) {
    const listing = (c.shop || []).find(s => s.id === uid) || {};
    kit.push({ listingId: uid, kind: "printer_upgrade", label: listing.label || uid });
  }
  c.deployKit = kit;
  state.hub.tenebrium = c.tenebrium;
  if (state.hub.factionBanks) {
    state.hub.factionBanks.nullmercs = c.tenebrium;
    state.hub.factionBanks.ashwalkers = c.tenebrium;
  }
}
export async function tryBuy(listingId) {
  if (state.buyBusy) return toast("Purchase already in flight…", "err");
  const c = commerce();
  const item = (c.shop || []).find(s => s.id === listingId);
  if (!item) return toast("Unknown listing", "err");
  recomputeShopAvailability();
  if (!item.available) return toast(item.blockedReason || "Locked", "err");
  const tcost = Number(item.tenebriumCost || 0);
  const mcost = Number(item.metalCostK != null ? item.metalCostK : item.creditCost || 0);

  // Live path: mutate campaign_state via the kernel → story engine purchase_listing
  if (state.hostLive) {
    state.buyBusy = true;
    document.querySelectorAll(`[data-buy="${CSS.escape(listingId)}"]`).forEach(b => { b.disabled = true; });
    try {
      toast("Purchasing…");
      const { ok, status, data } = await api.purchase(listingId);
      if (!ok || data.ok === false) return toast((data && (data.error || data.reason)) || `Buy failed (${status})`, "err");
      if (data.commerce) state.hub.commerce = data.commerce;
      if (data.tenebrium != null) state.hub.tenebrium = data.tenebrium;
      if (data.aces) state.hub.aces = data.aces;
      recomputeShopAvailability();
      renderShop();
      renderBadges();
      logLine(`Bought ${item.label} (−${tcost} Tnb, −${(mcost * 1000).toLocaleString()} metal) · campaign bag live`);
      toast(`Bought ${item.label}`, "ok");
      await pullHubState();
      return;
    } catch (e) {
      return toast("Purchase error: " + e.message, "err");
    } finally {
      state.buyBusy = false;
      document.querySelectorAll(`[data-buy="${CSS.escape(listingId)}"]`).forEach(b => { if (!b.closest(".listing.locked")) b.disabled = false; });
    }
  }

  // Map-only demo bag — does not touch campaign_state
  c.tenebrium = Number(c.tenebrium || 0) - tcost;
  c.metalK = metalKOf(c) - mcost;
  delete c.scrapCredits;
  delete c.credits;
  c.owned = c.owned || {};
  c.upgrades = c.upgrades || {};
  if (item.kind === "printer_upgrade") {
    c.upgrades[listingId] = { installedAtMission: state.hub.missionNumber || 1, requires: item.requires };
  } else {
    const prev = c.owned[listingId] || {};
    const qty = (item.kind === "purchase_package") ? (Number(prev.qty || 0) + 1) : 1;
    c.owned[listingId] = { qty, loan: !!item.loan, unitDef: item.unitDef, loanCount: item.loan ? item.count : null, count: item.count, kind: item.kind, source: "hub_demo_buy", delivery: item.delivery || null };
    item.ownedQty = qty;
  }
  c.ledger = c.ledger || [];
  c.ledger.push({ op: "hub_demo_purchase", listingId, tcost, metalCostK: mcost, at: new Date().toISOString() });
  const etaNote = (item.delivery && (item.delivery.summary || item.delivery.etaText)) ? ` · ${item.delivery.summary || item.delivery.etaText}` : "";
  recomputeShopAvailability();
  renderShop();
  renderBadges();
  renderCompany();
  logLine(`Acquired ${item.label} (−${tcost} Tnb, −${(mcost * 1000).toLocaleString()} metal)${etaNote}. Demo bag only until campaign settle.`);
  toast(`Acquired ${item.label}${etaNote ? " — " + (item.delivery.etaText || "inbound") : ""} (demo)`, "ok");
  downloadJson(`hub_purchase_${listingId}.json`, {
    schemaVersion: "verdance-hub-purchase-demo/1.0", listingId, label: item.label, tenebriumCost: tcost, metalCostK: mcost,
    bag: { tenebrium: c.tenebrium, metalK: c.metalK, owned: c.owned, upgrades: c.upgrades },
    note: "Hub demo mutation. Live: PLAY.bat → POST /api/purchase.",
  });
}

// The reserve: the army the company built and lifted home. At the drop the player picks what
// boards, up to the lift limit (metal value; it grows with every sortie brought home). The
// kernel clamps the same way, so this is a view of the rule, not the rule.
//
// One row per unit type, with how many board and − / + (playtest, 2026-11-04: 22 identical kit
// tiles read as noise). Builders stay home unless the job is in the Rock Jungle: whoever is not on
// the drop is at base, and constructors there build the camp (owner call, 2026-11-04). One toggle
// brings them along.
import { state } from "./state.js";
import { $, esc } from "./render.js";

const HOME = "the_rock_jungle";
function surface() { return state.hub.reserve || { units: [], liftCap: 0, suggested: {} }; }
const row = (def) => (surface().units || []).find(u => u.unitDef === def) || {};
const valueOf = (def) => row(def).value || 0;
const atHome = () => !!(state.plan && state.plan.mapId === HOME);
export function bringValue(bring) {
  return Object.entries(bring || {}).reduce((s, [d, n]) => s + valueOf(d) * n, 0);
}
export function resetReserveBring() {
  const s = surface();
  state.reserveBring = { ...((atHome() ? s.suggestedHome : s.suggested) || s.suggested || {}) };
}
export function reserveBring() {
  if (!state.reserveBring) resetReserveBring();
  return state.reserveBring;
}

const builders = () => (surface().units || []).filter(u => u.builder);
const buildersAboard = (bring) => builders().some(u => (bring[u.unitDef] || 0) > 0);

function setCount(def, n) {
  const bring = reserveBring();
  const cap = Number(surface().liftCap) || 0;
  const have = row(def).count || 0;
  n = Math.max(0, Math.min(have, n));
  const others = bringValue(bring) - valueOf(def) * (bring[def] || 0);
  const v = valueOf(def);
  if (v > 0) n = Math.min(n, Math.max(0, Math.floor((cap - others) / v)));
  if (n) bring[def] = n; else delete bring[def];
}

// Bring the builders along, or leave them home to build. Bringing them makes room on a full lift by
// leaving the cheapest fighters home first, one at a time, until the builders fit.
function toggleBuilders() {
  const bring = reserveBring();
  if (buildersAboard(bring)) { for (const u of builders()) delete bring[u.unitDef]; return; }
  const cap = Number(surface().liftCap) || 0;
  const want = Math.min(cap, builders().reduce((s, u) => s + u.value * u.count, 0));
  const fighters = (surface().units || []).filter(u => !u.builder).sort((a, b) => a.value - b.value);
  for (const u of fighters) {
    while ((bring[u.unitDef] || 0) > 0 && cap - bringValue(bring) < want) {
      bring[u.unitDef] -= 1;
      if (!bring[u.unitDef]) delete bring[u.unitDef];
    }
  }
  for (const u of builders()) setCount(u.unitDef, u.count);
}

export function renderReserve(locked) {
  const host = $("drop-reserve");
  if (!host) return;
  const s = surface();
  const padRule = `<p class="rv-rule">Only what stands on the pad when you extract comes home. Anything left in the field stays there.</p>`;
  if (!(s.units || []).length) {
    host.innerHTML = `<div class="drop-squad-kicker">The reserve</div>` +
      `<p class="hint">Nothing in reserve yet. What you build, raise or capture and get onto the pad comes home and waits here.</p>` + padRule;
    return;
  }
  const bring = reserveBring();
  const used = bringValue(bring);
  const cap = Number(s.liftCap) || 0;
  const room = cap - used;
  const bs = builders();
  const bOn = buildersAboard(bring);
  const builderLine = bs.length
    ? `<div class="rv-builders"><span>${bOn
        ? (atHome() ? `Builders come along to build the camp.` : `Builders come along, so nobody builds at base this time.`)
        : (atHome() ? `Builders stay at base. Bring them to build the camp.` : `Builders stay at base and build the camp while you are away.`)}</span>` +
      (locked ? "" : `<button type="button" class="btn-ghost" data-rv-builders="1">${bOn ? "Leave them home" : "Bring them"}</button>`) + `</div>`
    : "";
  const rows = (s.units || []).map(u => {
    const n = bring[u.unitDef] || 0;
    const canAdd = !locked && n < u.count && u.value <= room;
    const canDrop = !locked && n > 0;
    return `<li class="rv-row${n ? " on" : ""}${u.builder ? " builder" : ""}">` +
      `<span class="rv-name">${esc(u.name)}</span>` +
      `<span class="rv-each">${Math.round(u.value)} each</span>` +
      `<span class="rv-step">` +
        `<button type="button" data-rv-minus="${esc(u.unitDef)}" aria-label="One fewer ${esc(u.name)}" ${canDrop ? "" : "disabled"}>−</button>` +
        `<b>${n}</b><small>of ${u.count}</small>` +
        `<button type="button" data-rv-plus="${esc(u.unitDef)}" aria-label="One more ${esc(u.name)}" ${canAdd ? "" : "disabled"}>+</button>` +
      `</span></li>`;
  }).join("");
  host.innerHTML =
    `<div class="drop-squad-kicker">The reserve · lift <b>${Math.round(used)}</b> of ${cap}` +
    (locked ? "" : ` <button type="button" class="btn-ghost rv-suggest" data-rv-suggest="1">Suggested</button>`) + `</div>` +
    `<div class="rv-meter"><i style="width:${cap ? Math.min(100, used / cap * 100).toFixed(1) : 0}%"></i></div>` +
    `<p class="rv-note">Lift is how much one drop can carry, in metal value. It grows by ${s.perSortie} with each sortie you bring home.</p>` +
    builderLine +
    `<ul class="rv-rows">${rows}</ul>` + padRule;
}

export function installReserve() {
  const host = $("drop-reserve");
  if (!host) return;
  host.addEventListener("click", ev => {
    const b = ev.target.closest("button");
    if (!b || b.disabled) return;
    const bring = reserveBring();
    if (b.dataset.rvSuggest) resetReserveBring();
    else if (b.dataset.rvBuilders) toggleBuilders();
    else if (b.dataset.rvPlus) setCount(b.dataset.rvPlus, (bring[b.dataset.rvPlus] || 0) + 1);
    else if (b.dataset.rvMinus) setCount(b.dataset.rvMinus, (bring[b.dataset.rvMinus] || 0) - 1);
    renderReserve(false);
  });
}

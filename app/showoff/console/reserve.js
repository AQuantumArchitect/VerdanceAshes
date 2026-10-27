// The reserve: the army the company built and lifted home. At the drop the player picks what
// boards, up to the lift limit (metal value; it grows with every sortie brought home). The
// kernel clamps the same way, so this is a view of the rule, not the rule.
import { state } from "./state.js";
import { $, esc } from "./render.js";

function surface() { return state.hub.reserve || { units: [], liftCap: 0, suggested: {} }; }
const valueOf = (def) => (surface().units.find(u => u.unitDef === def) || {}).value || 0;
export function bringValue(bring) {
  return Object.entries(bring || {}).reduce((s, [d, n]) => s + valueOf(d) * n, 0);
}
export function resetReserveBring() { state.reserveBring = { ...(surface().suggested || {}) }; }
export function reserveBring() {
  if (!state.reserveBring) resetReserveBring();
  return state.reserveBring;
}

// Kits (owner call, 2026-10-27): the reserve boards in packets, not one unit at a time, the way a
// hero brings a pack. A kit is one unit type, about KIT_VALUE of metal value (at least one unit);
// the last kit of a type takes what is left. Clicking a kit puts all of it aboard or none.
const KIT_VALUE = 500;
function kits() {
  const out = [];
  for (const u of surface().units || []) {
    const per = Math.max(1, Math.round(KIT_VALUE / Math.max(1, u.value)));
    for (let left = u.count, k = 0; left > 0; k++) {
      const n = Math.min(per, left);
      out.push({ id: `${u.unitDef}#${k}`, unitDef: u.unitDef, name: u.name, n, value: n * u.value, k });
      left -= n;
    }
  }
  return out;
}
// Which kits the current bring covers: a type's kits fill in order.
function kitsOn(bring) {
  const on = new Set(), left = { ...(bring || {}) };
  for (const kit of kits()) {
    if ((left[kit.unitDef] || 0) >= kit.n) { on.add(kit.id); left[kit.unitDef] -= kit.n; }
  }
  return on;
}

export function renderReserve(locked) {
  const host = $("drop-reserve");
  if (!host) return;
  const s = surface();
  if (!(s.units || []).length) {
    host.innerHTML = `<div class="drop-squad-kicker">The reserve</div><p class="hint">Nothing in reserve yet. What you build, raise or capture and get onto the pad comes home and waits here, packed into kits.</p>`;
    return;
  }
  const bring = reserveBring();
  const used = bringValue(bring);
  const cap = Number(s.liftCap) || 0;
  const on = kitsOn(bring);
  const cards = kits().map(kit => {
    const isOn = on.has(kit.id);
    const prevOn = kit.k === 0 || on.has(`${kit.unitDef}#${kit.k - 1}`);
    const can = !locked && (isOn || (prevOn && used + kit.value <= cap));
    return `<button type="button" class="rv-kit${isOn ? " on" : ""}" data-kit="${esc(kit.id)}" ${can ? "" : "disabled"}>` +
      `<div class="rk-name">${esc(kit.name)} ×${kit.n}</div>` +
      `<div class="rk-meta">${Math.round(kit.value)} metal value · ${isOn ? "aboard" : "at camp"}</div></button>`;
  }).join("");
  host.innerHTML =
    `<div class="drop-squad-kicker">The reserve · lift <b>${Math.round(used)}</b> / ${cap}` +
    `<span class="rv-note"> · grows ${s.perSortie} with each successful sortie</span>` +
    (locked ? "" : ` <button type="button" class="btn-ghost rv-suggest" data-rv-suggest="1">Suggested</button>`) + `</div>` +
    `<div class="rv-meter"><i style="width:${cap ? Math.min(100, used / cap * 100).toFixed(1) : 0}%"></i></div>` +
    `<div class="rv-kits">${cards}</div>`;
}

export function installReserve() {
  const host = $("drop-reserve");
  if (!host) return;
  host.addEventListener("click", ev => {
    const b = ev.target.closest("button");
    if (!b || b.disabled) return;
    if (b.dataset.rvSuggest) resetReserveBring();
    else if (b.dataset.kit) {
      const kit = kits().find(k => k.id === b.dataset.kit);
      if (!kit) return;
      const bring = reserveBring();
      const on = kitsOn(bring).has(kit.id);
      // Kits of one type board in order: switching one off takes it and the ones after it.
      const before = kits().filter(k => k.unitDef === kit.unitDef && k.k < kit.k).reduce((n, k) => n + k.n, 0);
      const n = on ? before : before + kit.n;
      if (n) bring[kit.unitDef] = n; else delete bring[kit.unitDef];
    }
    renderReserve(false);
  });
}

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

export function renderReserve(locked) {
  const host = $("drop-reserve");
  if (!host) return;
  const s = surface();
  const units = s.units || [];
  if (!units.length) {
    host.innerHTML = `<div class="drop-squad-kicker">The reserve</div><p class="hint">Nothing in reserve yet. What you build and get onto the pad comes home and waits here.</p>`;
    return;
  }
  const bring = reserveBring();
  const used = bringValue(bring);
  const cap = Number(s.liftCap) || 0;
  const rows = units.map(u => {
    const n = bring[u.unitDef] || 0;
    const canUp = !locked && n < u.count && used + u.value <= cap;
    return `<div class="rv-row${n ? " on" : ""}"><span class="rv-name">${esc(u.name)}</span>` +
      `<span class="rv-val">${u.value}</span>` +
      `<button type="button" class="btn-ghost" data-rv="${esc(u.unitDef)}" data-d="-1" ${locked || !n ? "disabled" : ""}>−</button>` +
      `<b>${n}</b><span class="rv-of">/ ${u.count}</span>` +
      `<button type="button" class="btn-ghost" data-rv="${esc(u.unitDef)}" data-d="1" ${canUp ? "" : "disabled"}>+</button></div>`;
  }).join("");
  host.innerHTML =
    `<div class="drop-squad-kicker">The reserve · lift <b>${Math.round(used)}</b> / ${cap}` +
    `<span class="rv-note"> · grows ${s.perSortie} with each sortie brought home</span>` +
    (locked ? "" : ` <button type="button" class="btn-ghost rv-suggest" data-rv-suggest="1">Suggested</button>`) + `</div>` +
    `<div class="rv-meter"><i style="width:${cap ? Math.min(100, used / cap * 100).toFixed(1) : 0}%"></i></div>` +
    `<div class="rv-list">${rows}</div>`;
}

export function installReserve() {
  const host = $("drop-reserve");
  if (!host) return;
  host.addEventListener("click", ev => {
    const b = ev.target.closest("button");
    if (!b || b.disabled) return;
    if (b.dataset.rvSuggest) resetReserveBring();
    else if (b.dataset.rv) {
      const bring = reserveBring(), d = b.dataset.rv;
      const n = Math.max(0, (bring[d] || 0) + Number(b.dataset.d));
      if (n) bring[d] = n; else delete bring[d];
    }
    renderReserve(false);
  });
}

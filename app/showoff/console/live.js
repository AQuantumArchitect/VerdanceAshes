// Live board: while a dropped sortie is being fought, BAR's minimap widget writes what the
// company sees (LuaUI/Config/verdance/live.json) and the kernel serves it at /api/live.
// This paints it over the belief board: zones in sight light up, our heroes stand where they
// are, the pad and objective counts ride a strip on top. Belief itself is untouched; it moves
// only at homecoming. LAW holds: the report is our sight and our people, never the ground.
import { state, BOARDS } from "./state.js";
import { api } from "./api.js";
import { $, esc } from "./render.js";
import { focusMapAndRepaint } from "./board.js";

let wasLive = false;

function minuteOf(frame) { return Math.floor((Number(frame) || 0) / 1800); }

function paintLive(live) {
  const host = $("board-live");
  if (!host) return;
  const board = live && live.live && BOARDS[live.mapId];
  document.body.classList.toggle("is-live", !!board);
  if (!board) { host.innerHTML = ""; return; }
  const mx = Number(live.mapX) || 1, mz = Number(live.mapZ) || 1;
  const sight = [], marks = [], padLine = [];
  for (const z of board.zones || []) {
    if (z.zoneId === live.padZoneId && z.shape) padLine.push(`<path class="lv-pad" d="${z.shape.d}" fill-rule="evenodd"/>`);
    const r = (live.zones || {})[z.zoneId];
    if (!r || !z.shape) continue;
    if (r.eta > 0.02) sight.push(`<path class="lv-sight" d="${z.shape.d}" fill-rule="evenodd" style="--eta:${Math.min(1, r.eta).toFixed(2)}"/>`);
    const a = z.anchor || { x: 0.5, z: 0.5 };
    const bits = [];
    if (r.found) bits.push(`<b class="${r.found === "empty" ? "muted" : "bad"}">${r.found === "empty" ? "○" : "✗"}</b>`);
    if (r.enemy > 0) bits.push(`<span class="bad">${Math.round(r.enemy)} seen</span>`);
    if (bits.length) marks.push(`<div class="lv-mark" style="left:${a.x * 100}%;top:${a.z * 100}%">${bits.join(" ")}</div>`);
  }
  const heroes = (live.heroes || []).filter(h => Number.isFinite(Number(h.x)) && Number.isFinite(Number(h.z))).map(h => {
    const down = h.state && h.state !== "alive";
    const cls = ["lv-hero", down ? "down" : "", h.onPad ? "on-pad" : "", (h.hp != null && h.hp < 0.35 && !down) ? "hurt" : ""].filter(Boolean).join(" ");
    return `<div class="${cls}" style="left:${(h.x / mx) * 100}%;top:${(h.z / mz) * 100}%" title="${esc(h.name || h.id)}${down ? " · down" : ""}"><i></i><span>${esc(h.name || h.id)}</span></div>`;
  });
  const pad = live.pad || {}, obj = live.objective || {};
  host.innerHTML =
    `<svg class="lv-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${sight.join("")}${padLine.join("")}</svg>` +
    marks.join("") + heroes.join("") +
    `<div class="lv-strip"><b>LIVE</b> · minute ${minuteOf(live.frame)} · pad: ${pad.people || 0} people, ${pad.units || 0} units` +
    (pad.enemy > 0 ? ` · <span class="bad">${pad.enemy} enemy on the pad</span>` : "") +
    (obj.total > 0 ? ` · objective ${obj.done || 0}/${obj.total}` : "") + `</div>`;
}

async function poll() {
  if (!state.hostLive) { paintLive(null); return; } // file:// open, no kernel: nothing to watch
  let live = null;
  try { live = await api.live(); } catch { live = null; }
  const on = !!(live && live.live && BOARDS[live.mapId]);
  // Going live follows the fight to its map once; after that the player may look elsewhere.
  if (on && !wasLive && live.mapId !== state.focusMap) focusMapAndRepaint(live.mapId, "Live sortie");
  wasLive = on;
  paintLive(on && live.mapId === state.focusMap ? live : null);
}

export function installLive() {
  poll();
  setInterval(poll, 2000);
}

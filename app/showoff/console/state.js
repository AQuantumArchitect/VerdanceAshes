// Shared hub state. Everything the hub knows lives here: the hub surface the kernel
// serves (state.hub), the drop plan being marked, and the console session (which
// workspace, which thread, the narrative poll). Pure readers of that state live here too.

export const H = window.HUB_STATE || {};
export const BOARDS = window.ZONE_BOARDS || {};
export const CREW = window.CREW_PACKS || { core: ["vane", "ketha"], heroes: {}, seatCap: 3, startWalletTnb: 5 };

export const state = {
  hub: JSON.parse(JSON.stringify(H)),
  focusMap: null,
  hostLive: false,
  hostBase: "", // "" = same-origin; else http://127.0.0.1:8770
  hostInfo: null,
  markMode: "capture",
  plan: null,
  log: [],
  rhoSel: { i: 0, j: 0 },
  lastResultAt: null,
  crewBand: [], // preamble picks; after seal = who drops (at-base = owned − this)
  dropping: false, // true while /api/deploy is in flight
  buyBusy: false,
  warm: { phase: "idle", locked: false, timer: null, poll: null, startedAt: 0 },
  selectedZoneId: null, // last marked / clicked theater zone (recruit tease)
  padNote: null, // {mapId,text} — why the last Pad click was refused (shown in #marks-sum)
  sortieSynced: false, // after seal, keep local Dropping↔Base picks across hub pulls
  knownCompanyIds: null, // sealed members already sorted Dropping↔Base (absorb new joins)
};

export const session = {
  workspace: "operations", narrative: null, selectedThread: null, selectedHero: null,
  selectedZone: null, allThreads: false, signature: "", error: "",
};

// Camp face state (Home workspace): the DERIVE faces the kernel serves.
export const camp = { camp: null, intel: null, chronicle: null, exposure: null, busy: false, mapFilter: null, heroPick: null, zonePick: null };

export function list(xs) { return Array.isArray(xs) ? xs.map(String) : []; }
export function clamp01(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0;
}

export function companySurface() { return (state.hub && state.hub.company) || {}; }
export function companySealed() {
  const c = companySurface();
  return !!(c.sealed || (state.hub && state.hub.flags && state.hub.flags.companySealed));
}
export function commerce() {
  return state.hub.commerce || { shop: [], deployKit: [], tenebrium: 0, metalK: 0, owned: {}, upgrades: {} };
}
export function metalKOf(c) {
  c = c || commerce();
  if (c.metalK != null) return Number(c.metalK || 0);
  // Legacy scrapCredits / credits → treat as already-migrated km$ if small, else ÷10.
  const legacy = Number(c.scrapCredits != null ? c.scrapCredits : c.credits || 0);
  return legacy > 40 ? Math.floor(legacy / 10) : legacy;
}
export function arcMax() { return (state.hub.arc && state.hub.arc.maxCaptureMarks) || 1; }

export function prettyMap(id) {
  if (!id) return "—";
  const r = (state.hub.regions || []).find(x => x.mapId === id);
  if (r && r.displayName) return r.displayName;
  return String(id).replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}
export function prettyMapShort(mapId) {
  const id = String(mapId || "");
  const shorts = {
    greenest_fields: "Fields", the_rock_jungle: "Jungle", eye_of_horus: "Horus", koom_valley: "Koom",
    tabula: "Tabula", ancient_bastion: "Bastion", all_that_simmers: "Simmer",
  };
  if (shorts[id]) return shorts[id];
  const full = prettyMap(id);
  if (full && full !== "—" && full.length <= 14) return full;
  return id.replace(/_/g, " ") || "?";
}
export function sessionLabel(mode) {
  const m = String(mode || "");
  if (m === "map_travel" || m === "reload_travel") return "On the road";
  if (m === "same_map") return "Holding this ground";
  return m ? m.replace(/_/g, " ") : "Holding this ground";
}
export function repLabel(k) {
  const map = { armada: "Armada", cortex: "Cortex", nullmercs: "Null Mercs", ashwalkers: "Ashwalkers", sev: "Sev" };
  return map[k] || String(k).replace(/_/g, " ");
}
export function jobLabel(kind) {
  return ({
    eco_raid: "Raid their economy",
    seize_lane: "Seize and hold the lane",
    strike_relay: "Cut the relay",
    destroy_key_structure: "Break the key structure",
    hive_clear_or_bypass: "Clear or bypass the hive",
    gate_control: "Hold the gate",
    home_clear: "Clear the home wilds",
    fortify_zone: "Fortify and secure the zone",
    secure_foothold: "Secure the foothold",
    home_founding: "Found the camp — dig in",
  })[kind] || String(kind || "Sortie").replace(/_/g, " ");
}

// Zone label from the theater board, the belief frame, or the zone boards. Never invents.
export function zoneLabelAny(zoneId, mapId) {
  if (!zoneId) return "";
  const th = state.hub.theater || {};
  const hit = (th.zones || []).find(z => z && z.zoneId === zoneId);
  if (hit && hit.label) return hit.label;
  const bz = (state.hub.belief && state.hub.belief.zones) || {};
  if (bz[zoneId] && bz[zoneId].label) return bz[zoneId].label;
  for (const mid of [mapId, th.mapId, state.focusMap].filter(Boolean)) {
    const z = ((BOARDS[mid] || {}).zones || []).find(x => x.zoneId === zoneId);
    if (z && z.label) return z.label;
  }
  return String(zoneId);
}

export function deployChoicesAll() {
  return ((state.hub.node || {}).choices || []).filter(ch => String(ch.kind || "") === "deploy");
}
export function deployChoicesForMap(mapId) {
  const mid = String(mapId || "");
  return deployChoicesAll().filter(ch => String((ch.effect || {}).mapId || "") === mid);
}
export function availableMaps() {
  const h = state.hub || {};
  const ids = [];
  const push = (id) => {
    const m = String(id || "").trim();
    if (!m || ids.includes(m)) return;
    ids.push(m);
  };
  // Journey maps first — scales as builder emits more theaters.
  for (const ch of deployChoicesAll()) push((ch.effect || {}).mapId);
  push(h.sessionHomeMap);
  push(h.node && h.node.sortieMapId);
  push(h.node && h.node.regionHint);
  push(h.homeCamp && h.homeCamp.mapId);
  // Respect region selectable flags when present (locked maps stay off chips).
  const regionOk = new Map((h.regions || []).map(r => [r.mapId, r.selectable !== false]));
  const filtered = ids.filter(id => regionOk.size === 0 || regionOk.get(id) !== false);
  if (filtered.length) return filtered;
  // Fresh / empty fallback — the opening pair.
  return ["greenest_fields", "the_rock_jungle"];
}
export function ensureFocusMapAvailable() {
  const maps = availableMaps();
  if (!maps.length) return null;
  if (maps.includes(state.focusMap)) return state.focusMap;
  const preferred =
    (state.hub.node && (state.hub.node.sortieMapId || state.hub.node.regionHint)) ||
    state.hub.sessionHomeMap ||
    maps[0];
  state.focusMap = maps.includes(preferred) ? preferred : maps[0];
  return state.focusMap;
}

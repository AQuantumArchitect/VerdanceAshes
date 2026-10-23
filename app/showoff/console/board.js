// Theater board: belief paint, pad legality, marks and the route (pass-six encoding).
// LAW: the board paints what the COMPANY believes, never the truth. Every colour, glyph
// and gate below reads from theater.zones[] (belief rows) or hub.belief.zones; nothing
// reads an authoritative control string.
import { renderStory } from "./story.js";
import { state, session, BOARDS, clamp01, prettyMap, prettyMapShort, jobLabel, deployChoicesForMap, availableMaps, ensureFocusMapAvailable, companySurface } from "./state.js";
import { $, esc, escape, pretty, field, toast, logLine } from "./render.js";
import { refreshTheaterForFocus, updateDeployGate } from "./operations.js";
import { renderCompany } from "./company.js";
import { renderRegions } from "./system.js";
import { renderHeadline } from "./shell.js";

const RIM_THRESHOLD = 0.28;
// Faction names the board may colour. Colour means "we believe this faction holds it".
const FACTION_KEYS = new Set(["armada", "cortex", "nullmercs", "wild", "raptors", "raptor", "scavengers", "legion"]);
const PAD_THREAT_MAX = 0.4;
const FACTION_WORD = { armada: "Armada", cortex: "Cortex", nullmercs: "Null Mercs", wild: "Wild", raptors: "Raptors", raptor: "Raptors", scavengers: "Scavengers", legion: "Legion" };

/* ---- geometry ---------------------------------------------------------------- */
export function edgeScore(z) {
  if (z && z.edgeScore != null) return Number(z.edgeScore);
  const b = (z && z.bounds) || {};
  const cx = ((Number(b.xMin) || 0) + (Number(b.xMax) || 1)) / 2;
  const cz = ((Number(b.zMin) || 0) + (Number(b.zMax) || 1)) / 2;
  return Math.min(cx, 1 - cx, cz, 1 - cz);
}
export function isRimZone(z) { return edgeScore(z) <= RIM_THRESHOLD; }
// The zone's anchor in board units — where the game puts the pad and where labels sit.
export function zoneCenter(z) {
  const p = zonePoint(z);
  return { x: p.x * 100, y: p.z * 100 };
}
function zonePoint(z) {
  const a = z && z.anchor;
  if (a && a.x != null && a.z != null) return { x: Number(a.x), z: Number(a.z) };
  const b = (z && z.bounds) || {};
  return { x: ((Number(b.xMin) || 0) + (Number(b.xMax) || 1)) / 2, z: ((Number(b.zMin) || 0) + (Number(b.zMax) || 1)) / 2 };
}
function zoneIsWet(z) {
  if (!z) return true;
  if (z.dry === false) return true;
  if (z.dry === true) return false;
  const role = String(z.role || "").toLowerCase();
  const tags = (z.tags || []).map(t => String(t).toLowerCase());
  return role.includes("spillway") || role.includes("island") || tags.includes("flood");
}
function padSpanOk(z) {
  const b = (z && z.bounds) || {};
  const sx = Math.abs((Number(b.xMax) || 1) - (Number(b.xMin) || 0));
  const sz = Math.abs((Number(b.zMax) || 1) - (Number(b.zMin) || 0));
  return sx <= 0.50 && sz <= 0.50 && sx >= 0.02 && sz >= 0.02;
}
function nearestDryPad(mapId, targetId) {
  const zones = ((BOARDS[mapId] || {}).zones) || [];
  const target = zones.find(z => z.zoneId === targetId);
  if (!target) return null;
  const o = zonePoint(target);
  let best = null, bestD = 1e9;
  for (const z of zones) {
    if (!z || z.zoneId === targetId || zoneIsWet(z) || !padSpanOk(z)) continue;
    const p = zonePoint(z);
    const d = Math.hypot(p.x - o.x, p.z - o.z);
    if (d < bestD) { bestD = d; best = z; }
  }
  return best;
}
function padIsNear(mapId, zoneId, targetId) {
  const zones = ((BOARDS[mapId] || {}).zones) || [];
  const zone = zones.find(z => z.zoneId === zoneId);
  const target = zones.find(z => z.zoneId === targetId);
  const near = nearestDryPad(mapId, targetId);
  if (!zone || !target || !near || zone.zoneId === targetId) return false;
  if (zoneIsWet(zone) || !padSpanOk(zone)) return false;
  const o = zonePoint(target);
  const d = Math.hypot(zonePoint(zone).x - o.x, zonePoint(zone).z - o.z);
  const best = Math.hypot(zonePoint(near).x - o.x, zonePoint(near).z - o.z);
  return d <= best + 0.12 && d <= Math.max(0.40, best + 0.02);
}

/* ---- claims, contracts, belief ------------------------------------------------- */
function claimRecordFor(mapId, zoneId) {
  const mid = String(mapId || ""), zid = String(zoneId || "");
  if (!mid || !zid) return null;
  for (const led of [state.hub.nodeClaims, state.hub.claimedNodes]) {
    if (!led || typeof led !== "object") continue;
    const byMap = led[mid];
    if (byMap && typeof byMap === "object" && !Array.isArray(byMap)) {
      const rec = byMap[zid];
      if (rec) return rec;
    }
    if (Array.isArray(led.nodes)) {
      const hit = led.nodes.find(n => n && n.mapId === mid && n.zoneId === zid);
      if (hit) return hit;
    }
  }
  return null;
}
function openContractFor(mapId, zoneId) {
  const mid = String(mapId || ""), zid = String(zoneId || "");
  return (state.hub.captureContracts || []).find(c => c && c.mapId === mid && (c.targetZoneId || c.zoneId) === zid) || null;
}
function intelFor(mapId, zoneId) {
  const theater = state.hub.theater || {};
  let base = null;
  if (theater.mapId === mapId && theater.intelByZone && theater.intelByZone[zoneId]) {
    base = Object.assign({}, theater.intelByZone[zoneId]);
  } else if (theater.mapId === mapId) {
    const hit = (theater.zones || []).find(z => z.zoneId === zoneId);
    if (hit) base = Object.assign({}, hit);
  }
  const claim = claimRecordFor(mapId, zoneId);
  const open = openContractFor(mapId, zoneId);
  if (!base && !claim && !open) return null;
  const out = base || { zoneId, label: (open && open.label) || zoneId, control: "unknown", confidence: open ? "contract" : "estimated", openTarget: false, claimed: false, preferred: false, hazard: 0 };
  if (claim) {
    out.claimed = true;
    if (!out.control || out.control === "unknown") out.control = claim.newControl || claim.patron || "ashwalkers";
  }
  if (open) {
    out.openTarget = true;
    out.preferred = true;
    if (open.label) out.label = open.label;
  }
  return out;
}
function beliefRow(mapId, zoneId) {
  const theater = state.hub.theater || {};
  if (theater.mapId === mapId) {
    const hit = (theater.zones || []).find(z => z && z.zoneId === zoneId);
    if (hit && (hit.believed || hit.state)) return hit;
  }
  const bz = (state.hub.belief && state.hub.belief.zones) || {};
  const row = bz[zoneId];
  if (row && (!row.mapId || row.mapId === mapId)) return row;
  return null;
}
export function beliefOf(mapId, zoneId) {
  const row = beliefRow(mapId, zoneId);
  const out = { believed: "dark", control: "unknown", confidence: 0, state: "dark", ageMin: null, source: null, threat: null, surprise: null, people: [], holding: 0, known: false };
  if (!row) {
    // Old hub states (no belief frame): our own claim ledger is company knowledge, not truth.
    const claim = claimRecordFor(mapId, zoneId);
    if (claim) Object.assign(out, { believed: "ours", control: "ashwalkers", confidence: 0.5, state: "stale", source: "claim", known: true });
    return out;
  }
  const control = String(row.control || "unknown").toLowerCase();
  let believed = String(row.believed || "").toLowerCase();
  // A row with no belief word is not a belief: say "nobody looked", never a made-up percentage.
  if (!["ours", "held", "empty", "dark", "unsure"].includes(believed)) believed = "dark";
  const st = String(row.state || "").toLowerCase();
  out.believed = believed;
  out.control = control;
  out.confidence = clamp01(row.confidence);
  out.state = ["current", "stale", "dark"].includes(st) ? st : (believed === "dark" ? "dark" : "current");
  out.ageMin = row.ageMin == null ? null : Number(row.ageMin);
  out.source = row.source || null;
  out.threat = row.threat == null ? null : clamp01(row.threat);
  out.surprise = row.surprise && typeof row.surprise === "object" ? row.surprise : null;
  out.people = Array.isArray(row.people) ? row.people : [];
  out.holding = Math.max(0, Number(row.holding) || 0);
  out.known = true;
  return out;
}
function believedFaction(b) { return b && b.believed === "held" && FACTION_KEYS.has(b.control) ? b.control : null; }
function factionWord(f) {
  return ({ armada: "Armada", cortex: "Cortex", nullmercs: "Null Mercs", wild: "the wild", raptors: "Raptors", raptor: "Raptors", scavengers: "Scavengers", legion: "the Legion" })[f] || f;
}
function believedWord(b) {
  const f = believedFaction(b);
  return b.believed === "ours" ? "ours"
    : b.believed === "held" ? (f ? `held by ${factionWord(f)}` : "held — by whom, unseen")
    : b.believed === "empty" ? "empty"
    : b.believed === "dark" ? "dark — nobody has looked"
    : "unsure";
}
function ageWord(min) {
  if (min == null || !Number.isFinite(Number(min))) return "never looked";
  const m = Math.max(0, Math.round(Number(min)));
  if (m < 60) return `looked ${m} min ago`;
  if (m < 48 * 60) return `looked ${Math.round(m / 60)} h ago`;
  return `looked ${Math.round(m / 1440)} d ago`;
}
export function beliefCountsForMap(mapId) {
  const boardN = (((BOARDS[mapId] || {}).zones) || []).length;
  const rows = [], seen = new Set();
  const th = state.hub.theater || {};
  if (th.mapId === mapId) (th.zones || []).forEach(r => { if (r && r.zoneId && (r.believed || r.state)) { rows.push(r); seen.add(r.zoneId); } });
  Object.values((state.hub.belief && state.hub.belief.zones) || {}).forEach(r => {
    if (r && r.mapId === mapId && !seen.has(r.zoneId)) { rows.push(r); seen.add(r.zoneId); }
  });
  let current = 0, stale = 0, dark = 0;
  rows.forEach(r => {
    const st = String(r.state || "dark").toLowerCase();
    if (st === "current") current += 1; else if (st === "stale") stale += 1; else dark += 1;
  });
  if (boardN > rows.length) dark += boardN - rows.length;
  return { current, stale, dark };
}
// Exposure (their eyes on OUR holdings — our side of the mirror only).
export function padExposed(zoneId) {
  const arm = (((state.hub.exposure || {}).factions) || {}).armada || {};
  if ((arm.known || []).includes(zoneId)) return "known";
  if ((arm.suspected || []).includes(zoneId)) return "suspected";
  return null;
}

/* ---- legality ----------------------------------------------------------------- */
function zoneInOps(mapId, z) {
  if (!z) return false;
  const intel = intelFor(mapId, z.zoneId) || {};
  if (intel.claimed || intel.openTarget || intel.preferred) return true;
  const b = beliefOf(mapId, z.zoneId);
  if (b.known && b.state !== "dark") return true; // anything the company has looked at is mission ground
  if (b.people.length || b.holding > 0) return true;
  if (isLegalLanding(mapId, z)) return true;
  const m = (state.plan && state.plan.marks) || {};
  if (m.deployZoneId === z.zoneId || m.extractZoneId === z.zoneId) return true;
  if ((m.captureZoneIds || []).includes(z.zoneId)) return true;
  return false;
}
function isBelievedOurs(mapId, zoneId) { return beliefOf(mapId, zoneId).believed === "ours"; }
// Pad legality from belief: ours, OR a rim zone believed empty/dark with low believed
// threat, OR the camp's own next pad. Returns the reason either way so an illegal click can say WHY.
export function padLegality(mapId, z) {
  if (!z) return { ok: false, why: "no such zone" };
  const camp = state.hub.camp || {};
  if (camp.nextPadZoneId && camp.nextPadZoneId === z.zoneId && (!camp.nextPadMapId || camp.nextPadMapId === mapId)) {
    return { ok: true, why: "the camp's next pad" };
  }
  const b = beliefOf(mapId, z.zoneId);
  const pct = `${Math.round(b.confidence * 100)}%`;
  if (b.believed === "ours") return { ok: true, why: `believed ours · ${pct}` };
  if (b.believed === "held") return { ok: false, why: `believed held · ${pct}` };
  if (b.believed === "unsure") return { ok: false, why: `unsure what is there · ${pct}` };
  if (!isRimZone(z)) return { ok: false, why: "not a rim" };
  if ((b.threat ?? 0) > PAD_THREAT_MAX) return { ok: false, why: `threat too high · ${Math.round((b.threat || 0) * 100)}%` };
  return { ok: true, why: b.believed === "dark" ? "rim · nobody has looked" : `rim · believed empty · ${pct}` };
}
export function isLegalLanding(mapId, z) { return padLegality(mapId, z).ok; }

/* ---- default route --------------------------------------------------------------- */
// Far dry corners stay on the board as pads the player can mark, but a sortie default pad
// snaps to the near shore (one pad: you lift where you landed). The camp's own pad is never snapped away from.
export function snapGroundRoute(mapId, marks) {
  const targetId = (marks.captureZoneIds || [])[0];
  if (!targetId) return;
  const camp = state.hub.camp || {};
  const onCampPad = !!(camp.nextPadZoneId && marks.deployZoneId === camp.nextPadZoneId && (!camp.nextPadMapId || camp.nextPadMapId === mapId));
  if (!onCampPad) {
    const near = nearestDryPad(mapId, targetId);
    if (near && !padIsNear(mapId, marks.deployZoneId, targetId)) {
      const zones = ((BOARDS[mapId] || {}).zones) || [];
      const nearZ = zones.find(z => z.zoneId === near.zoneId);
      // Snap only onto a pad belief says is legal; otherwise keep the current pick.
      if (nearZ && isLegalLanding(mapId, nearZ)) marks.deployZoneId = near.zoneId;
    }
  }
  marks.extractZoneId = marks.deployZoneId; // one pad: in and out are the same zone
}
export function defaultMarks(mapId) {
  const zones = (BOARDS[mapId] || {}).zones || [];
  // Pad: the camp's next pad when it is on this map; else a legal pad from belief
  // (believed ours first, then quiet rim lanes).
  const camp = state.hub.camp || {};
  const campPad = camp.nextPadZoneId && (!camp.nextPadMapId || camp.nextPadMapId === mapId) ? zones.find(z => z.zoneId === camp.nextPadZoneId) : null;
  const legal = zones.filter(z => isLegalLanding(mapId, z));
  const byEdge = legal.slice().sort((a, b) => {
    const owned = (z) => (isBelievedOurs(mapId, z.zoneId) ? 0 : 1);
    const lane = (z) => (z && z.interMapLane) ? 0 : 1;
    return (owned(a) - owned(b)) || (lane(a) - lane(b)) || (edgeScore(a) - edgeScore(b));
  });
  const rim = byEdge.filter(z => isRimZone(z));
  const lanes = rim.filter(z => z.interMapLane);
  const owned = byEdge.filter(z => isBelievedOurs(mapId, z.zoneId));
  const deployPool = owned.length ? owned : (lanes.length ? lanes : (rim.length ? rim : byEdge));
  const deploy =
    campPad ||
    deployPool.find(z => z.deployDefault) ||
    deployPool.find(z => z.interMapLane) ||
    deployPool.find(z => /start|staging|shelf|camp|muster/i.test(String(z.role || "") + " " + (z.tags || []).join(" "))) ||
    deployPool[0] ||
    zones[0];
  const theater = state.hub.theater || {};
  const openId = ((theater.openTargets || [])[0] || {}).zoneId;
  const caps = zones.filter(z => z.capturable || z.preferredObjective);
  const pick =
    (openId && zones.find(z => z.zoneId === openId)) ||
    caps.find(z => z.preferredObjective && z.zoneId !== (deploy && deploy.zoneId)) ||
    caps.find(z => z.preferredObjective) ||
    caps[0] ||
    zones[0];
  return {
    deployZoneId: deploy && deploy.zoneId,
    extractZoneId: deploy && deploy.zoneId, // one pad: you leave from where you landed
    captureZoneIds: pick ? [pick.zoneId] : [],
  };
}

/* ---- wild recruits (wrecks this Drop can seed) ------------------------------------- */
export function wildRecruitsForMap(mapId) {
  const raw = companySurface().wild;
  const mid = String(mapId || "");
  return (Array.isArray(raw) ? raw.filter(w => w && typeof w === "object") : []).filter(w => String(w.mapId || "") === mid);
}
function markedZonesForPlan(plan) {
  const m = (plan && plan.marks) || {};
  const out = [];
  for (const z of (m.captureZoneIds || [])) if (z) out.push(String(z));
  if (m.deployZoneId) out.push(String(m.deployZoneId));
  if (m.extractZoneId) out.push(String(m.extractZoneId));
  return [...new Set(out)];
}
// Mirror tools/company_v1.field_recruits_for_map: marked pads seat first (up to 3), then
// ambient fills to limit 2. Teasing EVERY wild pad lied about which wrecks Drop actually bakes.
export function predictedFieldRecruits(mapId, plan) {
  const mid = String(mapId || "");
  const marked = new Set(markedZonesForPlan(plan));
  const rows = wildRecruitsForMap(mid).map(w => {
    const zone = String(w.zoneId || "");
    let belief = 0.15;
    if (zone && marked.has(zone)) belief += 10;
    const mode = String((w.recruit && w.recruit.type) || w.recruitMode || "wreck_rez");
    if (mode === "wreck_rez" || mode === "retrieve_stash" || mode === "capture") belief += 0.2;
    return { id: w.id || w.heroId, name: w.name, mapId: mid, zoneId: zone || null, recruit: w.recruit || { type: mode }, beliefScore: belief };
  });
  rows.sort((a, b) => (b.beliefScore - a.beliefScore) || String(a.id).localeCompare(String(b.id)));
  const limit = 2;
  if (marked.size) {
    const must = rows.filter(r => r.zoneId && marked.has(r.zoneId)).slice(0, 3);
    const rest = rows.filter(r => !must.includes(r));
    const floor = Math.max(limit, must.length);
    const out = must.slice();
    for (const r of rest) { if (out.length >= floor) break; out.push(r); }
    return out.length ? out : rows.slice(0, Math.max(1, limit));
  }
  return rows.slice(0, Math.max(1, limit));
}
export function wildRecruitAtZone(mapId, zoneId) {
  if (!zoneId) return null;
  const plan = state.plan || { mapId, marks: {} };
  return predictedFieldRecruits(mapId, plan).find(r => String(r.zoneId || "") === String(zoneId)) || null;
}

/* ---- paint ---------------------------------------------------------------------- */
function drawRouteArrows(plan, zones) {
  const svg = $("board-route");
  if (!svg) return;
  const m = (plan && plan.marks) || {};
  const byId = Object.fromEntries((zones || []).map(z => [z.zoneId, z]));
  const pad = byId[m.deployZoneId];
  const target = byId[(m.captureZoneIds || [])[0]];
  const parts = [];
  // One pad: pad → wound → back to the pad. A double-headed line in the warn token (out)
  // with a good-token return head; colours from the tokens.
  parts.push(`<defs>
      <marker id="arr-out" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0,0 L5,2.5 L0,5 Z" class="route-out"/></marker>
      <marker id="arr-back" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto-start-reverse"><path d="M0,0 L5,2.5 L0,5 Z" class="route-back"/></marker>
    </defs>`);
  if (pad && target) {
    // Stop short of both anchors so the heads sit beside the zone names, not on them.
    const p = zoneCenter(pad), q = zoneCenter(target);
    const len = Math.hypot(q.x - p.x, q.y - p.y) || 1, trim = Math.min(6, len / 4);
    const ux = (q.x - p.x) / len, uy = (q.y - p.y) / len;
    const a = { x: p.x + ux * trim, y: p.y + uy * trim }, b = { x: q.x - ux * trim, y: q.y - uy * trim };
    parts.push(`<line class="route-line" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke-width="0.9" stroke-opacity="0.9" marker-start="url(#arr-back)" marker-end="url(#arr-out)"/>`);
    const mx = a.x + (b.x - a.x) * 0.18, my = a.y + (b.y - a.y) * 0.18;
    parts.push(`<text class="route-return" x="${mx}" y="${my}" dy="-1.2" text-anchor="middle" font-size="3.2" stroke-width="0.3" paint-order="stroke">↩</text>`);
  }
  svg.innerHTML = parts.join("");
}

export function renderBoard() {
  if (!state.plan) refreshTheaterForFocus();
  const plan = state.plan;
  if (!plan) return;
  const zones = (BOARDS[plan.mapId] || { zones: [] }).zones || [];
  const el = $("board-zones");
  const title = $("theater-title");
  const sub = $("theater-sub");
  if (title) title.textContent = prettyMap(plan.mapId);
  if (sub) {
    const camp = (state.hub.homeCamp && state.hub.homeCamp.level) || 0;
    const flags = state.hub.flags || {};
    const homeNote = plan.mapId === "the_rock_jungle"
      ? (flags.homeCleared ? " · home cleared" : ` · camp L${camp}${flags.homeClearReady ? " · clear ready" : " · need Tnb to scale"}`)
      : "";
    sub.textContent = `${jobLabel(plan.contractKind)} · ${(plan.deployAces || []).join(", ") || "your aces"}${homeNote}`;
  }
  const lzMode = state.markMode === "pad";
  if (!zones.length) {
    el.innerHTML = `<div class="board-empty">No zone board for <b>${esc(plan.mapId)}</b>. Run tools/build_zone_boards_v1.py.</div>`;
    drawRouteArrows(plan, []);
  } else {
    const m = plan.marks || {};
    // Big zones first so nested ones sit on top — the same order the in-game board paints.
    const byArea = zones.slice().sort((a, b) => ((b.shape && b.shape.cells) || 0) - ((a.shape && a.shape.cells) || 0));
    el.innerHTML = byArea.map(z => {
      const b = z.bounds || { xMin: 0, xMax: 0.2, zMin: 0, zMax: 0.2 };
      const shape = z.shape || { d: "", box: [(b.xMin || 0) * 100, (b.zMin || 0) * 100, ((b.xMax || 0) - (b.xMin || 0)) * 100, ((b.zMax || 0) - (b.zMin || 0)) * 100] };
      const [left, top, w, h] = shape.box;
      const pt = zonePoint(z);
      const lx = w > 0 ? ((pt.x * 100 - left) / w) * 100 : 50;
      const ly = h > 0 ? ((pt.z * 100 - top) / h) * 100 : 50;
      const intel = intelFor(plan.mapId, z.zoneId) || {};
      const bel = beliefOf(plan.mapId, z.zoneId);
      const legal = padLegality(plan.mapId, z);
      const cls = ["zone"];
      if (z.capturable) cls.push("capturable");
      cls.push(isRimZone(z) ? "rim-eligible" : "midfield");
      if (legal.ok) cls.push("lz-eligible", "pad-legal");
      else if (lzMode) cls.push("pad-illegal");
      if (lzMode) cls.push("mode-lz");
      if (intel.openTarget || intel.preferred) cls.push("open-target");
      if (intel.claimed) cls.push("claimed");
      // Belief paint: state + (believed faction) + freshness. No truth classes.
      cls.push("bel-" + bel.believed);
      const fac = believedFaction(bel);
      if (fac) cls.push("fac-" + fac.replace(/[^a-z]/g, ""));
      if (bel.state === "stale") cls.push("st-stale");
      const eyes = padExposed(z.zoneId);
      if (eyes) cls.push("exp-" + eyes);
      if (m.deployZoneId === z.zoneId) cls.push("deploy-mark");
      if ((m.captureZoneIds || []).includes(z.zoneId)) cls.push("capture-mark");
      const inOps = zoneInOps(plan.mapId, z);
      if (!inOps) cls.push("fog");
      // Only the mission's reported recruit belongs on the tactical map.
      const recruitHere = wildRecruitAtZone(plan.mapId, z.zoneId);
      if (recruitHere) cls.push("has-recruit");
      const chip = recruitHere ? `<div class="zone-chip">rez</div>` : ((intel.openTarget || intel.preferred) ? `<div class="zone-chip">open</div>` : "");
      const recruitTitle = recruitHere ? ` · THIS DROP wreck: ${recruitHere.name || recruitHere.id}` : "";
      const fogNote = inOps ? "" : " · outside ops";
      // Glyph row: surprise (✗ / ○), exposure (◉), threat bar, people ⚑, holdings ■, dark ?
      const sp = bel.surprise;
      const spEmpty = sp && String(sp.believed).toLowerCase() === "held" && String(sp.found).toLowerCase() === "empty";
      const spBadge = sp ? `<span class="z-surprise ${spEmpty ? "muted" : "bad"}" title="believed ${esc(sp.believed)}, found ${esc(sp.found)}">${spEmpty ? "○" : "✗"}</span>` : "";
      const eyeBadge = eyes === "known" ? `<span class="z-eyes" title="Armada has eyes on this holding">◉</span>` : "";
      const threatBar = (bel.threat != null && bel.threat > 0 && bel.confidence > 0.2)
        ? `<i class="z-threat" style="width:${Math.round(bel.threat * 100)}%" title="believed threat ${Math.round(bel.threat * 100)}%"></i>` : "";
      const anyWounded = bel.people.some(p => p && p.wounded);
      const peopleNames = bel.people.map(p => (p && (p.name || p.heroId)) || "").filter(Boolean);
      const peopleGlyph = bel.people.length ? `<span class="z-people ${anyWounded ? "bad" : "good"}" title="${esc(peopleNames.join(", "))}">⚑ ${bel.people.length}</span>` : "";
      const holdGlyph = bel.holding > 0 ? `<span class="z-hold" title="${bel.holding} of our structures left here">■ ${bel.holding}</span>` : "";
      const darkGlyph = bel.believed === "dark" ? `<span class="z-q" aria-hidden="true">?</span>` : "";
      const tipBits = [
        z.label || z.zoneId,
        `believed ${believedWord(bel)}`,
        bel.known ? `${Math.round(bel.confidence * 100)}%` : null,
        bel.state,
        ageWord(bel.ageMin),
        (bel.threat != null && bel.confidence > 0.2) ? `threat ${Math.round(bel.threat * 100)}%` : null,
        peopleNames.length ? `ours here: ${peopleNames.join(", ")}` : null,
        bel.holding > 0 ? `holdings ${bel.holding}` : null,
        sp ? `✗ believed ${sp.believed}, found ${sp.found}` : null,
        eyes === "known" ? "Armada has eyes on it" : eyes === "suspected" ? "Armada may suspect it" : null,
        legal.ok ? `pad: ${legal.why}` : (lzMode ? `no pad: ${legal.why}` : null),
      ].filter(Boolean);
      // The div spans the zone's box; the svg path is the zone (authored cells, as in-game) and is
      // the only part that takes the pointer, so nested zones click true. style= carries geometry,
      // the label point and the confidence custom property only; colour comes from classes.
      const hatch = eyes === "known" ? `<path class="z-exposed" d="${shape.d}" fill-rule="evenodd"/>` : "";
      return `<div role="button" tabindex="0" class="${cls.join(" ")}" data-zone="${esc(z.zoneId)}"
          data-believed="${esc(bel.believed)}" data-control="${esc(bel.control)}" data-conf="${bel.confidence.toFixed(2)}" data-state="${esc(bel.state)}"
          style="left:${left}%;top:${top}%;width:${w}%;height:${h}%;--conf:${bel.confidence.toFixed(2)};--lx:${lx.toFixed(1)}%;--ly:${ly.toFixed(1)}%"
          title="${esc(tipBits.join(" · "))}${esc(recruitTitle)}${fogNote}">
          <svg class="z-shape" viewBox="${left} ${top} ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path class="z-area" d="${shape.d}" fill-rule="evenodd"/>${hatch}</svg>
          <div class="z-anchor">
            <div class="zone-label">${esc(z.label || z.zoneId)}</div>${chip}
            <span class="z-corner">${spBadge}${eyeBadge}</span>
            ${darkGlyph}
            <span class="z-foot">${peopleGlyph}${holdGlyph}</span>
            ${threatBar}
          </div>
        </div>`;
    }).join("");
    el.querySelectorAll(".zone").forEach(z => {
      z.onclick = () => markZone(z.dataset.zone);
      z.onkeydown = ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); z.click(); } };
    });
    drawRouteArrows(plan, zones);
  }
  const m = plan.marks || {};
  const zoneName = (id) => {
    if (!id) return "—";
    const z = zones.find(x => x.zoneId === id);
    return (z && z.label) || id;
  };
  const modeLabel = ({ capture: "wound", pad: "pad" })[state.markMode] || state.markMode;
  const opsLit = zones.filter(z => zoneInOps(plan.mapId, z)).length;
  const legalN = zones.filter(z => isLegalLanding(plan.mapId, z)).length;
  const padEyes = padExposed(m.deployZoneId);
  const padNote = state.padNote && state.padNote.mapId === plan.mapId ? `<br><span class="warn">${esc(state.padNote.text)}</span>` : "";
  $("marks-sum").innerHTML =
    `<b>Pad</b> ${esc(zoneName(m.deployZoneId))} → <b>wound</b> ${(m.captureZoneIds || []).map(z => esc(zoneName(z))).join(", ") || "—"} → back to <b>${esc(zoneName(m.deployZoneId))}</b><br>` +
    `marking <b>${esc(modeLabel)}</b> · ${legalN} legal pad${legalN === 1 ? "" : "s"} (△) · ops ${opsLit}/${zones.length || 0} zones · believed ours, or a quiet rim` +
    (padEyes === "known" ? `<br><span class="bad">◉ Armada has eyes on this pad.</span>` : "") +
    padNote;
  updateIntelligence(session.narrative, plan.mapId);
  updateDeployGate();
}

export function markZone(zoneId) {
  const plan = state.plan;
  if (!plan) return;
  const z = ((BOARDS[plan.mapId] || {}).zones || []).find(x => x.zoneId === zoneId);
  const m = plan.marks;
  if (state.markMode === "pad") {
    const legal = padLegality(plan.mapId, z);
    if (!legal.ok) {
      const why = `${(z && z.label) || zoneId}: no pad — ${legal.why}`;
      state.padNote = { mapId: plan.mapId, text: why };
      toast(why, "err");
      renderBoard();
      return;
    }
    state.padNote = null;
    m.deployZoneId = zoneId; // ONE pad: in and out share the zone; the stamp schema is unchanged.
    m.extractZoneId = zoneId;
  } else {
    const caps = m.captureZoneIds || [];
    const i = caps.indexOf(zoneId);
    if (i >= 0) caps.splice(i, 1);
    else {
      if (caps.length >= (plan.maxCaptureMarks || 1)) caps.shift();
      caps.push(zoneId);
    }
    m.captureZoneIds = caps;
  }
  state.selectedZoneId = zoneId; // last clicked zone drives the company recruit tease
  renderBoard();
  renderCompany();
  const seeded = wildRecruitAtZone(plan.mapId, zoneId);
  if (seeded) toast(`This Drop seeds wreck · ${seeded.name || seeded.id}`, "ok");
}

/* ---- map picker ---------------------------------------------------------------- */
export function focusMapAndRepaint(mapId, why) {
  state.focusMap = mapId;
  state.selectedZoneId = null;
  renderRegions();
  renderStory();
  refreshTheaterForFocus(); // repaints the map picker, the board and the company
  renderHeadline();
  logLine(`${why} → ${prettyMap(mapId)}`);
}
export function renderMapPicker() {
  const el = $("map-picker");
  if (!el) return;
  const focus = ensureFocusMapAvailable();
  const home = state.hub.sessionHomeMap || (state.hub.homeCamp && state.hub.homeCamp.mapId) || "the_rock_jungle";
  const maps = availableMaps();
  el.innerHTML = maps.map(mapId => {
    const n = deployChoicesForMap(mapId).length;
    const active = mapId === focus;
    const tags = [];
    if (mapId === home) tags.push(`<span class="tag-home">home</span>`);
    tags.push(`<span class="tag-count">${n} sortie${n === 1 ? "" : "s"}</span>`);
    return `<button type="button" class="map-chip${active ? " active" : ""}" data-map="${esc(mapId)}" role="tab" aria-selected="${active ? "true" : "false"}">
        <span class="mc-name">${esc(prettyMapShort(mapId))}</span>
        <span class="mc-meta">${tags.join("")}</span>
      </button>`;
  }).join("") || `<div class="theater-sub">No operational maps yet.</div>`;
  el.querySelectorAll(".map-chip").forEach(btn => {
    btn.onclick = () => {
      const mapId = btn.dataset.map;
      if (!mapId || mapId === state.focusMap) {
        refreshTheaterForFocus();
        renderHeadline();
        return;
      }
      focusMapAndRepaint(mapId, "Operational map");
    };
  });
}

/* ---- owner chip, intel line, zone inspector (belief words from the zone's data attributes) ---- */
// Never re-adds a truth class; never rewrites the belief tooltip.
function ownerFromBelief(zone) {
  const believed = zone.dataset.believed || "dark";
  const control = zone.dataset.control || "unknown";
  if (believed === "ours") return "● Ours";
  if (believed === "held") return FACTION_WORD[control] ? `◆ ${FACTION_WORD[control]}` : "◆ Held";
  if (believed === "empty") return "○ Empty";
  if (believed === "unsure") return "◌ Unsure";
  return "? Dark";
}
export function updateIntelligence(narrative, mapId) {
  document.querySelectorAll("#board-zones .zone").forEach(zone => {
    const record = narrative?.intelligence?.[`${mapId}:${zone.dataset.zone}`];
    const ownerText = ownerFromBelief(zone);
    // One word for who we believe holds it, and only when we believe someone does. Dark, empty
    // and unsure say it with the shape (hairline + ?, outline, dashes), as the in-game board does.
    const anchor = zone.querySelector(".z-anchor") || zone;
    let owner = zone.querySelector(".cc-owner");
    const believedHolder = ["ours", "held"].includes(zone.dataset.believed);
    if (believedHolder && !owner) { owner = document.createElement("span"); owner.className = "cc-owner"; anchor.append(owner); }
    if (!believedHolder && owner) { owner.remove(); owner = null; }
    if (owner && owner.textContent !== ownerText) owner.textContent = ownerText;
    const conf = Math.round(Number(zone.dataset.conf || 0) * 100);
    const st = zone.dataset.state || "dark";
    const name = zone.querySelector(".zone-label")?.textContent || zone.dataset.zone;
    const aria = `${name}. Believed ${ownerText.slice(2)}, ${conf}% sure, ${st}.${record ? " " + record.status + "." : ""}`;
    if (zone.getAttribute("aria-label") !== aria) zone.setAttribute("aria-label", aria);
  });
}
export function zoneInspector(zoneId, mapId, narrative) {
  const record = narrative?.intelligence?.[`${mapId}:${zoneId}`];
  const el = document.querySelector(`#board-zones .zone[data-zone="${CSS.escape(String(zoneId))}"]`);
  const believed = el ? ownerFromBelief(el).slice(2) : "Unknown";
  const conf = el ? Math.round(Number(el.dataset.conf || 0) * 100) : 0;
  const st = el ? (el.dataset.state || "dark") : "dark";
  return `<p class="cc-eyebrow">Map intelligence</p><h2>${escape(pretty(zoneId))}</h2>` +
    field("We believe", st === "dark" ? "Nobody has looked." : `${believed} · ${conf}% sure · ${st}`) +
    field("Knowledge", record?.status || (st === "dark" ? "Unknown" : "From the company's own looking")) +
    field("Source", record?.source || "No explicit battlefield observation is recorded.") +
    (record?.lastObservedTurn != null ? field("Last observed", `Completed sortie ${record.lastObservedTurn}. Conditions may have changed since then.`) : field("Last observed", "See the zone tooltip for how long ago the company looked.")) +
    field("Pad rules", "A pad is legal when we believe the zone is ours, when it is a quiet rim we believe empty or have not looked at, or when it is the camp's next pad. You leave from where you landed.") +
    field("Forecast", "Belief is not the ground. A route suggestion is not a promise of safety.");
}
export function installOverlays() {
  const bar = $("cc-overlays");
  const theater = $("theater");
  if (!bar || !theater) return;
  bar.addEventListener("change", e => theater.classList.toggle(`hide-${e.target.dataset.overlay}`, !e.target.checked));
}

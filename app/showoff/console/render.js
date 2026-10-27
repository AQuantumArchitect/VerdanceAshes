// Templates and DOM primitives shared by every workspace. No fetches, no state writes
// except the toast timer and the session log.
import { state, CREW, companySurface, jobLabel } from "./state.js";

export const $ = (id) => document.getElementById(id);
export const escape = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const esc = escape;
export const pretty = (value) => String(value || "Unknown").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
export const field = (label, text) => `<div class="cc-field"><h3>${escape(label)}</h3><p>${escape(text)}</p></div>`;

export function toast(msg, kind) {
  const el = $("toast");
  if (!el) return;
  el.textContent = msg;
  el.className = "status-toast show" + (kind ? " " + kind : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 4200);
}

// Session log — kept as state so a debrief can read what happened; no longer painted.
export function logLine(text) {
  state.log.unshift(text);
  state.log = state.log.slice(0, 12);
}

export function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1500);
}

/* ---- hero card ------------------------------------------------------------ */
export function crewPack(id) { return (CREW.heroes || {})[id] || {}; }
export function crewHeroName(id) {
  const h = crewPack(id);
  if (h && h.name) return h.name;
  const pool = companySurface().pool || [];
  const hit = pool.find(p => p && p.id === id);
  if (hit && hit.name) return hit.name;
  return id;
}
export function aceById(id) {
  const aces = (state.hub && state.hub.aces) || [];
  return aces.find(a => a && a.id === id) || null;
}
export function heroNameAny(id) {
  const ace = aceById(id);
  return (ace && ace.name) || crewHeroName(id) || String(id);
}
function crewChassisName(h) {
  const def = h && h.unitDef;
  const ch = (CREW.chassis || {})[def];
  if (ch && ch.label) return ch.label;
  if (!def) return "?";
  return String(def).replace(/^(leg|arm|cor)/, "");
}
function heroLevelXp(id, override) {
  const ace = override || aceById(id) || {};
  const pack = crewPack(id);
  const level = Number(ace.level || pack.level || 1) || 1;
  const xpRaw = ace.campaignXp != null ? ace.campaignXp : (pack.campaignXp != null ? pack.campaignXp : null);
  const xp = xpRaw != null ? Math.round(Number(xpRaw) || 0) : null;
  return { level, xp, rank: ace.rank || null, status: ace.status || null, wounds: ace.wounds || 0 };
}
function escortMeta(h) {
  return (h.escorts || []).map(e => {
    const label = e.label || ((CREW.chassis || {})[e.unitDef] || {}).label || e.unitDef || "?";
    return `${e.count || 1}× ${label}`;
  }).join(", ");
}
/** Flavor text must not carry prices — cost lives on the badge. */
function sanitizeHeroBlurb(text) {
  let s = String(text || "");
  s = s.replace(/\s*[—–-]\s*\d+\s*Tnb\b[^.]*/gi, "");
  s = s.replace(/\s*[—–-]\s*\d+\s*km\$\b[^.]*/gi, "");
  s = s.replace(/\(\s*\d+\s*Tnb\s*\)/gi, "");
  s = s.replace(/\(\s*\d+\s*km\$\s*\)/gi, "");
  s = s.replace(/\b\d+\s*Tnb\b/gi, "");
  s = s.replace(/\b\d+\s*km\$\b/gi, "");
  s = s.replace(/\bfree seat\b/gi, "");
  s = s.replace(/\bno Tnb stake\b/gi, "");
  s = s.replace(/\s{2,}/g, " ").replace(/\s+([.,;:])/g, "$1").trim();
  s = s.replace(/[—–-]\s*$/g, "").trim();
  return s;
}
function renderCostBadges(tnb, km, { showFree } = {}) {
  const bits = [];
  if (Number(tnb) > 0) bits.push(`<span class="hc-cost tnb">${Number(tnb)} Tnb</span>`);
  if (Number(km) > 0) bits.push(`<span class="hc-cost km">${(Number(km) * 1000).toLocaleString()} metal</span>`);
  if (!bits.length && showFree) bits.push(`<span class="hc-cost free">free</span>`);
  return bits.length ? `<div class="hc-cost-row">${bits.join("")}</div>` : "";
}
/**
 * Shared hero card — company intro, drop confirm, recruit slot. Level sits opposite
 * the name; XP under level. Hire cost is a badge — never buried in flavor text.
 */
export function renderHeroCard(opts) {
  const o = opts || {};
  const id = o.id || "";
  const h = o.pack || crewPack(id);
  const stats = heroLevelXp(id, o.ace);
  const name = o.name || crewHeroName(id);
  const tag = o.tag ? ` · ${o.tag}` : "";
  const chassis = o.chassis || crewChassisName(h);
  const packN = h.packTotal || 1;
  const escLines = escortMeta(h);
  const costTnb = o.costTnb != null ? Number(o.costTnb) : Number(h.hireTnb || 0);
  const costKm = o.costKm != null ? Number(o.costKm) : Number(h.hireKm || 0);
  const metaBits = [o.meta, chassis, packN > 1 ? `pack ×${packN}` : null, escLines || null].filter(Boolean);
  const meta = [...new Set(metaBits)].join(" · ");
  const blurb = sanitizeHeroBlurb(o.blurb != null ? o.blurb : (h.blurb || ""));
  const showFree = o.showFreeCost != null ? !!o.showFreeCost : !!o.pickable;
  const costHtml = o.hideCost ? "" : renderCostBadges(costTnb, costKm, { showFree });
  const classes = ["hero-card"]
    .concat(o.classes || [])
    .concat(o.compact ? ["compact"] : [])
    .concat(o.panel ? ["panel"] : [])
    .concat(stats.wounds ? ["wounded"] : [])
    .filter(Boolean).join(" ");
  // Earned campaign XP once there is some; before that, the start XP the pack's cost buys.
  const startXp = Number(h.startXp) || 0;
  const xpLine = stats.xp ? `xp ${stats.xp}` : (startXp > 0 ? `start xp ${startXp.toFixed(2)}` : (o.xpLabel || "green"));
  const levelLine = `L${stats.level}`;
  // Sticky peak: career rank (Green/Proven/…). "Runner" is a SPEED tag, not a rank.
  // Legacy "Blooded" read as wounded — display as Proven.
  let peakRaw = String(stats.rank || o.peak || "").trim();
  if (/^blooded$/i.test(peakRaw) || /^bloodied$/i.test(peakRaw)) peakRaw = "Proven";
  if (!peakRaw || /^runner$/i.test(peakRaw)) peakRaw = "Green";
  const peakNorm = peakRaw.toLowerCase().replace(/\s+/g, "");
  const peakClass = peakNorm ? `hc-peak peak-${esc(peakNorm)}` : "hc-peak peak-green";
  const packTags = [].concat(h.tags || [], h.traits || []).filter(Boolean);
  const tagLine = packTags.length ? packTags.map(t => String(t).replace(/_/g, " ")).join(" · ") : "";
  const attrs = [
    o.dataCrew ? `data-crew="${esc(o.dataCrew)}"` : "",
    o.disabled ? "disabled" : "",
    o.type === "button" || o.dataCrew ? `type="button"` : "",
  ].filter(Boolean).join(" ");
  const tagName = (o.type === "button" || o.dataCrew) ? "button" : "div";
  return `<${tagName} class="${classes}" ${attrs}>
      <div class="hc-name">${esc(name)}${esc(tag)}</div>
      <div class="hc-level" title="${esc(peakRaw)}">${esc(levelLine)}</div>
      <div class="${peakClass}" title="Career rank — not a movement perk">${esc(peakRaw)}</div>
      <div class="hc-meta">${esc(meta)}</div>
      <div class="hc-xp">${esc(xpLine)}</div>
      ${tagLine ? `<div class="hc-tags" title="Procedural tags (boost / nerf)">${esc(tagLine)}</div>` : ""}
      ${costHtml}
      <div class="hc-blurb">${esc(blurb)}</div>
    </${tagName}>`;
}

/* ---- narrative templates (rail, inspector, chronicle) ------------------------ */
export function operation(op) {
  if (!op) return field("Choose an operation", "Select a sortie in the operations rail to see its requirements, risks, and route.");
  // The job, how to win it, and the field's standing rules folded away (they read the same on every job).
  const sub = [pretty(op.mapId), op.kind ? jobLabel(op.kind) : ""].filter(Boolean).join(" · ");
  return `<p class="cc-eyebrow">${escape(sub)}${op.lean ? ` <span class="cc-lean">the world leans here</span>` : ""}</p>` +
    `<h3 class="cc-op-title">${escape(op.title)}</h3>` +
    field("The job", op.purpose) + field("To win", op.required) + (op.pays ? field("What it pays", op.pays) : "") +
    `<details class="cc-rules"><summary>Field rules</summary>` +
    field("Bringing it home", op.bringHome) + field("What you don't know", op.risks) + field("What changes", op.consequences) +
    `</details>`;
}

// One line for the operations rail: people of ours who are not at camp.
// rows: [{name, where: posted|transit|field, label, wounded}]
export function fieldLine(rows) {
  const list = (rows || []).filter(Boolean);
  if (!list.length) return "";
  const word = r => r.where === "transit" ? "on the road" : (r.label || "somewhere");
  return `<p class="cc-field-people" role="status">Left in the field: ${list.map(r => `<b class="${r.wounded ? "bad" : ""}">${escape(r.name)}</b> (${escape(word(r))}${r.wounded ? " · wounded" : ""}${r.joinsThisDrop ? " · joins this drop" : ""})`).join(", ")}</p>`;
}

export function thread(t, live) {
  return `<p class="cc-eyebrow">Company matter / ${escape(t.stage)}</p><h2>${escape(t.title)}</h2>
    <p>${escape(t.opening)}</p>${field("Why now", t.reason)}
    ${t.history.length ? field("Commitment record", t.trust > 0 ? "A kept promise strengthens this thread." : t.trust < 0 ? "An unfinished promise remains part of this relationship." : "This situation is still unfolding.") : ""}
    ${t.remaining !== null ? field("Commitment window", `${t.remaining} completed sorties remain. Planning and reading do not consume turns.`) : ""}
    ${t.perspectives.map(p => `<blockquote><strong>${escape(pretty(p.speaker))}</strong><p>${escape(p.text)}</p></blockquote>`).join("")}
    ${reactions(t.reactions)}
    ${t.promise ? field("Your words", t.promise) : ""}${t.response ? field("Around the table", t.response) : ""}
    ${t.choices.map(c => `<div class="cc-choice"><button type="button" data-commit="${escape(c.id)}" ${live ? "" : "disabled"}>${escape(c.label)}</button><p class="cc-stance">${escape(c.stance || "Commitment")}</p><p>${escape(c.obligation)}</p><small>No resource cost. Records a narrative commitment; does not launch a battle.</small></div>`).join("")}
    ${t.stage === "Resolved" ? field("Remembered", t.remembered || t.callback) : ""}
    <h3>Available operations</h3>${t.operations.length ? t.operations.map(id => `<button type="button" data-operation="${escape(id)}">Plan: ${escape(t.operationLabels?.[id] || pretty(id))}</button>`).join("") : "<p>No compatible operation is currently available. Review the map after your next result.</p>"}
    <details><summary>Evidence and history</summary>${t.history.map(e => `<p>Turn ${escape(e.turn)} · ${escape(e.text)}</p>`).join("") || "<p>Based on the current campaign situation. No previous commitment is assumed.</p>"}</details>`;
}

export function chronicle(events) {
  return events.map(e => `<article class="cc-record"><p class="cc-eyebrow">Return ${escape(e.turn)} / ${escape(pretty(e.mapId))}</p>
    <h2>${escape(e.title)}</h2>${field("Company", e.participants.length ? e.participants.map(pretty).join(", ") : "Deployment record unavailable.")}
    ${e.wounded.length ? field("Wounded", e.wounded.map(pretty).join(", ")) : ""}
    ${field("Resources", Object.entries(e.resources).map(([k, v]) => `${pretty(k.replace("tenebrium", "Tenebrium "))}: ${v}`).join(" · ") || "No detailed resource ledger was supplied with this result.")}
    ${e.consequences.map(c => field(c.origin === "memory" ? "Remembered" : c.origin === "elsewhere" ? "While you were elsewhere" : c.origin === "campaign_update" ? "War assessment after your return" : "Because of this return", c.text)).join("")}
    <details><summary>Result evidence</summary><p>${escape(e.id)}</p><pre>${escape(JSON.stringify(e.credits, null, 2))}</pre></details></article>`).join("") || '<p class="cc-empty">Your first recorded return begins the chronicle. Older saves are not given invented history.</p>';
}

export function reactions(rows) {
  return (rows || []).map(r => `<article class="cc-reaction"><strong>${escape(pretty(r.speaker))}</strong><p>${escape(r.text)}</p><small>${r.basis === "kept" ? "After a kept promise" : r.basis === "unfinished" ? "After an unfinished promise" : "Remembering your words"}: “${escape(r.memory)}”</small></article>`).join("");
}

export function scene(s, live) {
  return `<details data-scene="${escape(s.id)}"><summary>${escape(s.title)} · ${s.pair.map(pretty).map(escape).join(" / ")}${s.decision ? " · Answered" : ""}</summary>${s.setup ? `<p>${escape(s.setup)}</p>` : ""}${s.beats.map(b => `<blockquote><strong>${escape(pretty(b.speaker))}</strong><p>${escape(b.text)}</p></blockquote>`).join("")}${s.decision ? field("Your answer", s.decision.words) + field("The response", s.decision.response) : (s.choices || []).map(c => `<div class="cc-choice"><button data-commit="${escape(c.id)}" ${live ? "" : "disabled"}>${escape(c.label)}</button><p class="cc-stance">${escape(c.stance)}</p><small>Records your position. No cost, deadline, or battle effect.</small></div>`).join("")}</details>`;
}

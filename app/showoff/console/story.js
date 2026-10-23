// Story state: where the company stands in its own story. The kernel scores the company's
// readings (a density matrix over eight readings, rho's diagonal) against each checkpoint in
// data/story/attractors.json; this draws that checkpoint graph, the six open questions, the
// path signals that pick the finale, and the path walked so far (one snapshot per sortie).
// Nothing here is the hidden world: it is what the company's own record says about it.
import { state } from "./state.js";
import { $, esc, pretty } from "./render.js";

const W = 640, H = 300, PADX = 70, PADY = 34;

function layout(nodes) {
  // Columns by first reach from the opening checkpoint; finales always last.
  const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
  const depth = {};
  const start = nodes[0] && nodes[0].id;
  if (start) {
    depth[start] = 0;
    const q = [start];
    while (q.length) {
      const id = q.shift();
      for (const e of byId[id].edges || []) {
        if (byId[e.to] && depth[e.to] == null && !byId[e.to].terminal) { depth[e.to] = depth[id] + 1; q.push(e.to); }
      }
    }
  }
  const inner = Math.max(0, ...Object.values(depth));
  for (const n of nodes) if (n.terminal) depth[n.id] = inner + 1; else if (depth[n.id] == null) depth[n.id] = inner;
  const cols = [];
  for (const n of nodes) (cols[depth[n.id]] = cols[depth[n.id]] || []).push(n);
  const pos = {};
  cols.forEach((col, c) => {
    if (c > 0) {
      // order by where the checkpoints feeding it sit (fewer crossings)
      const bary = n => {
        const ys = nodes.filter(p => pos[p.id] && (p.edges || []).some(e => e.to === n.id)).map(p => pos[p.id].y);
        return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : H / 2;
      };
      col.sort((a, b) => bary(a) - bary(b));
    }
    col.forEach((n, i) => {
      pos[n.id] = {
        x: PADX + (cols.length > 1 ? c * (W - 2 * PADX) / (cols.length - 1) : 0),
        y: PADY + (col.length > 1 ? i * (H - 2 * PADY) / (col.length - 1) : (H - 2 * PADY) / 2),
      };
    });
  });
  return pos;
}

function finaleLetter(s, id) {
  for (const [k, f] of Object.entries(s.finales || {})) {
    if (id === "finale_" + String(f.kind || "").split("_")[0]) return k;
  }
  return null;
}

function graphSvg(s) {
  const nodes = s.nodes || [];
  const pos = layout(nodes);
  const walked = (s.timeline || []).map(t => t.attractor).filter(Boolean);
  const visits = {};
  walked.forEach(a => { visits[a] = (visits[a] || 0) + 1; });
  const edges = [];
  for (const n of nodes) for (const e of n.edges || []) {
    const a = pos[n.id], b = pos[e.to];
    if (!a || !b) continue;
    edges.push(`<line class="sg-edge" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" marker-end="url(#sg-arrow)"><title>${esc(pretty(n.id))} → ${esc(pretty(e.to))}: ${esc(e.when || "")}</title></line>`);
  }
  // the path walked: one step per sortie that changed checkpoint
  const steps = walked.filter((a, i) => i === 0 || a !== walked[i - 1]).map(a => pos[a]).filter(Boolean);
  const trail = steps.length > 1 ? `<polyline class="sg-trail" points="${steps.map(p => `${p.x},${p.y}`).join(" ")}"/>` : "";
  const locked = (s.settledPairs || 0) < 3;
  const marks = nodes.map(n => {
    const p = pos[n.id];
    const f = Math.max(0, Math.min(1, Number(n.fidelity) || 0));
    const r = 9 + 13 * f;
    const here = n.id === s.current;
    const letter = n.terminal ? finaleLetter(s, n.id) : null;
    const picked = letter && letter === s.pathLeader;
    const cls = ["sg-node", here ? "here" : "", n.inside ? "inside" : "", n.terminal ? "finale" : "", picked ? "picked" : "", visits[n.id] ? "visited" : ""].filter(Boolean).join(" ");
    const why = (n.unmet || []).length ? `\nNot yet: ${n.unmet.join("; ")}` : "";
    const sub = here ? "you are here" : n.terminal ? (picked ? `path ${letter} · the finale` : `path ${letter}`) : (visits[n.id] ? `${visits[n.id]} sortie${visits[n.id] === 1 ? "" : "s"}` : "");
    return `<g class="${cls}" transform="translate(${p.x},${p.y})"><title>${esc(n.title)} · match ${(f * 100).toFixed(0)}%\n${esc(n.gloss || "")}${esc(why)}</title>` +
      `<circle r="${r.toFixed(1)}" style="--f:${f.toFixed(2)}"/>` +
      (n.terminal && locked ? `<text class="sg-lock" y="4">🔒</text>` : "") +
      `<text class="sg-label" y="${(r + 12).toFixed(1)}">${esc(n.title)}</text>` +
      (sub ? `<text class="sg-sub" y="${(r + 23).toFixed(1)}">${esc(sub)}</text>` : "") + `</g>`;
  }).join("");
  return `<svg class="sg-svg" viewBox="0 0 ${W} ${H + 20}" role="img" aria-label="Story checkpoints">` +
    `<defs><marker id="sg-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z"/></marker></defs>` +
    edges.join("") + trail + marks + `</svg>`;
}

function questionsHtml(s) {
  return (s.questions || []).map(q => {
    const settled = Math.max(0, Math.min(1, 1 - Number(q.c || 0)));
    const lean = q.leaning ? ` · leaning ${esc(pretty(q.leaning))}` : "";
    return `<div class="sg-q ${esc(q.status || "")}"><span class="sg-qtext">${esc(q.question || q.pair.join(" / "))}</span>` +
      `<span class="sg-qbar"><i style="width:${(settled * 100).toFixed(0)}%"></i></span><span class="sg-qstat">${esc(q.status || "open")}${lean}</span></div>`;
  }).join("");
}

function pathHtml(s) {
  const p = s.path || {};
  const max = Math.max(0.01, ...Object.values(p).map(Number));
  return ["A", "B", "C"].map(k => {
    const f = (s.finales || {})[k] || {};
    const lead = k === s.pathLeader;
    return `<div class="sg-path${lead ? " lead" : ""}"><b>${k}</b><span>${esc(f.title || k)}</span>` +
      `<span class="sg-qbar"><i style="width:${(Number(p[k] || 0) / max * 100).toFixed(0)}%"></i></span><span>${Number(p[k] || 0).toFixed(2)}</span></div>`;
  }).join("");
}

export function renderStory() {
  const host = $("story-graph");
  if (!host) return;
  const s = state.hub.storyState;
  if (!s || !(s.nodes || []).length) { host.innerHTML = ""; return; }
  const left = Math.max(0, (s.finaleAtMission || 11) - (s.missionNumber || 1));
  const cur = (s.nodes || []).find(n => n.id === s.current);
  host.innerHTML =
    `<h2>Where the story stands</h2>` +
    `<p class="sg-lede">${cur ? `The company's record reads closest to <b>${esc(cur.title)}</b>${s.inside ? "" : " (on its way there)"}.` : "No sorties yet."} ` +
    `Bigger, brighter checkpoints match the record better. The faint line is the road walked so far. ` +
    (left > 0 ? `The finale comes in ${left} sortie${left === 1 ? "" : "s"}.` : `The finale is now.`) + `</p>` +
    graphSvg(s) +
    `<div class="sg-cols"><div><h3>The open questions</h3><p class="sg-note">The finale checkpoints need three of these answered. A full bar is answered.</p>${questionsHtml(s)}</div>` +
    `<div><h3>Which finale</h3><p class="sg-note">The finale is picked by the path signal, which grows with each sortie's road.</p>${pathHtml(s)}</div></div>`;
}

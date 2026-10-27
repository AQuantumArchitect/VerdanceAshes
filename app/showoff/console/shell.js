// Shell: the four workspaces, the operations rail, the matters column and its inspector,
// the HUD badges, and the narrative poll that keeps them fresh.
import { state, session, CREW, commerce, metalKOf, prettyMap, sessionLabel, jobLabel } from "./state.js";
import { api } from "./api.js";
import { $, esc, escape, pretty, field, operation, thread, reactions, scene, fieldLine, toast } from "./render.js";
import { updateIntelligence, zoneInspector } from "./board.js";
import { onChoice } from "./operations.js";
import { companyMemberIds, fieldPeople } from "./company.js";
import { renderCampCard } from "./home.js";
import { renderChronicle } from "./chronicle.js";

const snapshot = () => ({ hub: state.hub, plan: state.plan, focusMap: state.focusMap, live: state.hostLive });

/* ---- HUD ------------------------------------------------------------------------- */
export function renderBadges() {
  const h = state.hub;
  const live = state.hostLive;
  const arc = h.arc || {};
  $("hud-title").textContent = `${(arc.title) || "First Scar"} · sortie ${h.missionNumber || 1}`;
  const home = h.sessionHomeMap || "the_rock_jungle";
  const sortie = (h.node && (h.node.sortieMapId || h.node.regionHint)) || state.focusMap || home;
  $("hud-badges").innerHTML = [
    `<span class="badge ${live ? "live" : "warn"}">${live ? "Campaign connected" : "Map only"}</span>`,
    `<span class="badge steam" title="Home you are founding">${esc(prettyMap(home))} home</span>`,
    `<span class="badge gold" title="Briefing / Drop theater">${esc(prettyMap(sortie))} sortie</span>`,
    `<span class="badge">${esc(sessionLabel(h.sessionMode))}</span>`,
    `<span class="badge tnb">Tenebrium ${h.tenebrium ?? commerce().tenebrium ?? 0}</span>`,
    `<span class="badge gold" title="Campaign metal available between sorties">${(metalKOf(commerce()) * 1000).toLocaleString()} metal</span>`,
  ].join("");
  $("foot-left").textContent = live ? `Campaign connected · sortie ${h.missionNumber || 1}` : `Map only · start PLAY.bat and keep its window open`;
}
// Kicker + title over the theater.
export function renderHeadline() {
  const h = state.hub;
  const node = h.node || {};
  const home = h.sessionHomeMap || node.regionHint;
  $("kicker").textContent = `${(h.arc && h.arc.title) || "First Scar"} · sortie ${h.missionNumber || 1} · ${prettyMap(home)}`;
  $("title").textContent = h.tagline || "The green is dying. Ashwalkers hold the line.";
}

/* ---- workspaces ------------------------------------------------------------------- */
const WORKSPACES = { operations: "workspace-operations", company: "col-aces", home: "workspace-home", chronicle: "workspace-chronicle" };
export function showWorkspace(name) {
  session.workspace = name;
  for (const [key, id] of Object.entries(WORKSPACES)) $(id).hidden = key !== name;
  document.querySelectorAll(".cc-nav button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.workspace === name)));
  $("theater-actions").hidden = name !== "operations";
  renderInspector();
}

function renderInspector() {
  const n = session.narrative;
  const snap = snapshot();
  const t = n?.threads?.find(t => t.id === session.selectedThread);
  if ($("cc-operation-details")) $("cc-operation-details").innerHTML = operation(n?.operations?.find(o => o.id === snap.plan?.choiceId));
  $("cc-map-details").hidden = !session.selectedZone;
  if (session.selectedZone) $("cc-map-details").innerHTML = "<summary>Selected map location</summary>" + zoneInspector(session.selectedZone, snap.focusMap, n);
  const inspector = $("cc-inspector");
  if (t && session.workspace === "operations") inspector.innerHTML = thread(t, snap.live);
  else if (session.workspace === "home") inspector.innerHTML = field("A practical home", "Camp level and home clearance reflect the existing simulation. Improvements cost 1 Tenebrium and 1,000 campaign metal.") + field("Resources", "Tenebrium supports construction capacity. Check each broker listing for its price and delivery conditions.");
  else if (session.workspace === "company" && session.selectedHero) {
    const ace = (snap.hub.aces || []).find(a => a.id === session.selectedHero);
    const pack = CREW.heroes?.[session.selectedHero] || {};
    const related = (n?.threads || []).filter(t => t.perspectives.some(p => p.speaker === session.selectedHero));
    inspector.innerHTML = ace ? `<p class="cc-eyebrow">Company member</p><h2>${escape(ace.name || pretty(ace.id))}</h2>` +
      field("Role", pack.blurb || ace.role || "Company specialist") + field("Condition", ace.status || "Status unavailable") +
      reactions((n?.reactions || []).filter(r => r.speaker === ace.id)) + field("Experience", `${ace.xp ?? "Not recorded"} campaign XP`) +
      field("Current commitments", related.filter(t => t.stage === "Committed").map(t => t.title).join(", ") || "No current narrative commitment involving this member.") +
      `<details><summary>Pack and progression</summary><pre>${escape(JSON.stringify({ unit: pack.unitDef, count: pack.packTotal, fieldEffect: pack.fieldEffect, wounds: ace.wounds, bonds: ace.bonds }, null, 2))}</pre></details>` :
      field("Member unavailable", "This member is no longer in the current company.");
  }
  else if (session.workspace === "company") inspector.innerHTML = field("Bring people with a purpose", "Core members travel with the company. Your initial three packs establish its strengths; later recruits expand your options.") + field("Readiness", "Inspect wounds and roles before deployment. Recovery, construction, and fighting power each serve a different need.") + field("Relationships", "Company scenes unlock from recorded shared deployments. Reading them never spends resources or advances a deadline.");
  else inspector.innerHTML = field("What kind of company are we?", "Select a company matter above to hear the disagreement and choose your response. These promises shape your history; operations on the left determine where you deploy.");
}

// One job card on the rail: the job's name (no "Lean ·" prefix: a pill says it), then the map and the
// kind of job, or the reason the company is pushing it.
function opCard(c, op, snap) {
  const raw = String(c.label || "Operation");
  const lean = !!(c.recommended || c.lean || raw.startsWith("Lean · "));
  const title = raw.replace(/^Lean · /, "");
  const kind = (c.effect && (c.effect.objectiveArchetype || c.effect.contractKind)) || "";
  const sub = (op && op.recommendation) || [prettyMap(c.effect && c.effect.mapId), kind ? jobLabel(kind) : ""].filter(Boolean).join(" · ");
  return `<button class="cc-operation" type="button" data-operation="${escape(c.id)}" ${c.disabled ? "disabled" : ""} aria-pressed="${c.id === snap.plan?.choiceId}">` +
    `${lean ? `<em class="cc-lean">lean</em>` : ""}<strong>${escape(title)}</strong><span>${escape(sub)}</span></button>`;
}
export function paint() {
  const n = session.narrative;
  const snap = snapshot();
  $("cc-pending").hidden = snap.hub.lastResult?.verdict !== "incomplete";
  // The finale shows from any map (it is the only operation left); everything else is per theater.
  const choices = (snap.hub.node?.choices || []).filter(c => c.kind === "deploy" && (c.finale || c.effect?.mapId === snap.focusMap));
  const over = snap.hub.node?.kind === "epilogue";
  const ranking = n?.operations || [];
  choices.sort((a, b) => ranking.findIndex(o => o.id === a.id) - ranking.findIndex(o => o.id === b.id));
  const signature = JSON.stringify([snap.hub.node?.kind, snap.hub.node?.choices?.length, n, snap.live, snap.focusMap, snap.plan?.choiceId, snap.hub.homeCamp, snap.hub.aces, snap.hub.lastResult, snap.hub.camp, session.allThreads, session.selectedThread, session.error]);
  updateIntelligence(n, snap.focusMap);
  if (signature === session.signature) return;
  session.signature = signature;
  const actionable = n?.threads?.filter(t => ["Available", "Committed", "Changed"].includes(t.stage)) || [];
  const shown = session.allThreads ? actionable : actionable.filter(t => n.recommended.includes(t.id));
  $("operations-rail").innerHTML = '<p class="cc-eyebrow">Company operations</p><h2>Where do we go next?</h2>' + fieldLine(fieldPeople()) +
    choices.slice(0, 3).map(c => opCard(c, ranking.find(o => o.id === c.id), snap)).join("") +
    (choices.length > 3 ? `<details><summary>All ${choices.length} operations</summary>${choices.slice(3).map(c => opCard(c, ranking.find(o => o.id === c.id), snap)).join("")}</details>` : "") +
    (over ? `<p class="cc-epilogue">${escape(snap.hub.node.text)}</p><p>The campaign is complete. The chronicle and the company remain.</p>`
      : !choices.length ? "<p>No operation on this theater. Select another map or refresh after your return.</p>" : "") +
    '<section id="cc-operation-details" aria-label="Selected operation"></section>';
  $("cc-matters").innerHTML = '<p class="cc-eyebrow">Around the company table</p><h2>Company matters</h2><p class="cc-matters-intro">People, principles, and promises.</p>' +
    shown.map(t => `<button class="cc-thread" type="button" data-thread="${escape(t.id)}" aria-pressed="${t.id === session.selectedThread}"><small>${escape(t.stage)}${t.remaining !== null ? ` · ${t.remaining} sorties left` : ""}</small><strong>${escape(t.title)}</strong><span>${escape(t.reason)}</span></button>`).join("") +
    (actionable.length > 3 ? `<button type="button" id="cc-more">${session.allThreads ? "Show recommended" : "Show all matters"}</button>` : "") +
    (session.error ? `<p role="status" class="cc-error">${escape(session.error)}</p>` : "");
  renderChronicle(n);
  renderCampCard();
  const camp = snap.hub.homeCamp || {};
  $("cc-home-status").innerHTML = field("Established", camp.cleared ? "Home ground secured" : `Camp level ${camp.level || 0}`) +
    field("Next milestone", camp.cleared ? "Hold what the company has built." : camp.clearReady ? "The home-clear operation is ready. Review its route and requirements." : "Raise the camp to prepare for clearing the surrounding wilds.") +
    field("Next improvement", camp.cleared ? "Home clear achieved." : `1 Tenebrium + 1,000 campaign metal. ${camp.canRaise ? "Available now." : "Gather the required resources before raising camp."}`);
  $("cc-company-members").innerHTML = "<h2>Know your company</h2><div class=\"cc-members\">" + (snap.hub.aces || []).filter(a => companyMemberIds().includes(a.id)).map(a => {
    const p = CREW.heroes?.[a.id] || {};
    return `<button type="button" data-hero="${escape(a.id)}"><strong>${escape(a.name || pretty(a.id))}</strong><span>${escape(a.status || "Condition unknown")}</span><p>${escape(p.blurb || a.role || "Company specialist")}</p></button>`;
  }).join("") + "</div>";
  const scenes = $("cc-company-scenes");
  const openScenes = new Set([...scenes.querySelectorAll("details[open][data-scene]")].map(el => el.dataset.scene));
  scenes.innerHTML = "<h2>The promises we live by</h2>" + (n?.leadership?.length ? n.leadership.slice(-6).reverse().map(c => `<blockquote><strong>${escape(c.stance)}</strong><p>${escape(c.words)}</p><small>Chosen after sortie ${escape(c.turn)}</small></blockquote>`).join("") : "<p>Your responses to company matters will be remembered here. A promise shows what you value; your returns show how you lived up to it.</p>") +
    "<h2>Between sorties</h2>" + (n?.scenes || []).map(s => scene(s, snap.live)).join("") + "<h2>How they see your command</h2>" + reactions(n?.reactions);
  scenes.querySelectorAll("[data-scene]").forEach(el => el.open = openScenes.has(el.dataset.scene));
  renderInspector();
}

/* ---- narrative poll ----------------------------------------------------------------- */
async function readNarrative() {
  const body = await api.narrative().catch(() => ({}));
  if (!body.ok) throw new Error(body.error || "Campaign information is unavailable.");
  return body.narrative;
}
async function commitChoice(choiceId) {
  const { ok, data: body } = await api.narrativeChoice({ choiceId, expectedRevision: session.narrative.revision, requestId: crypto.randomUUID() });
  if (!ok || !body.ok) throw new Error(body.error || "The commitment could not be recorded.");
  session.narrative = body.narrative;
  return body;
}
let polling = false;
async function refresh() {
  if (polling) return;
  polling = true;
  try {
    if (state.hostLive) { session.narrative = await readNarrative(); session.error = ""; }
    else session.narrative = state.hub.narrative || null;
    paint();
  } catch (err) {
    session.error = err.message;
    paint();
  } finally {
    polling = false;
  }
}

export function installShell() {
  document.querySelector(".cc-nav").onclick = e => { const b = e.target.closest("[data-workspace]"); if (b) showWorkspace(b.dataset.workspace); };
  $("cc-recover-result").onclick = () => $("btn-pull-result").click();
  // A pending result blocks the next Drop: no narrative deadline advances while sync is incomplete.
  document.addEventListener("click", e => {
    if (e.target.closest("#btn-deploy,#drop-confirm-go") && state.hub.lastResult?.verdict === "incomplete") {
      e.preventDefault();
      e.stopImmediatePropagation();
      toast("Recover the pending battle result before deploying again.");
    }
  }, true);
  $("board-zones").addEventListener("click", e => { const z = e.target.closest("[data-zone]"); if (z) { session.selectedZone = z.dataset.zone; renderInspector(); } });
  document.addEventListener("click", async e => {
    const op = e.target.closest("[data-operation]");
    const matter = e.target.closest("[data-thread]");
    const commit = e.target.closest("[data-commit]");
    const hero = e.target.closest("[data-hero]");
    if (hero) { session.selectedHero = hero.dataset.hero; session.selectedThread = null; session.selectedZone = null; showWorkspace("company"); renderInspector(); }
    if (op) { session.selectedZone = null; showWorkspace("operations"); onChoice(op.dataset.operation); paint(); renderInspector(); }
    if (matter) {
      showWorkspace("operations");
      session.selectedThread = matter.dataset.thread;
      session.selectedZone = null;
      const t = session.narrative.threads.find(t => t.id === session.selectedThread);
      if (t?.maps.length && !t.maps.includes(state.focusMap)) {
        const legalMaps = (state.hub.regions || []).filter(r => r.selectable !== false).map(r => r.mapId);
        const mid = t.maps.find(m => legalMaps.includes(m));
        if (mid) window.Verdance.focusMap(mid);
      }
      paint();
      renderInspector();
    }
    if (e.target.id === "cc-more") { session.allThreads = !session.allThreads; paint(); }
    if (commit) {
      commit.disabled = true;
      try { await commitChoice(commit.dataset.commit); session.error = ""; paint(); }
      catch (err) { session.error = err.message; paint(); }
      finally { commit.disabled = false; }
    }
  });
  showWorkspace("operations");
  refresh();
  setInterval(refresh, 3000);
  setInterval(paint, 500); // selection changes repaint without rebuilding the board or losing its position
}

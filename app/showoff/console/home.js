// The hearth talks, and the faces the folded chronicle reads (/api/camp, /api/intel,
// /api/exposure, /api/chronicle). The Home tab and its clock (rest, wait, scout, post, recall)
// are gone (owner call, 2026-11-04): scouting is a sortie's secondary, and whoever is off the
// drop is at base.
//
// Law: the hub shows INTEL, never truth. Zone rows come from the company's own belief frame
// (value/confidence/age/source). "dark" means nobody has looked. /api/exposure is our side of
// the mirror only; /api/divergence and /api/truth are dev faces the kernel refuses to the player.
import { state, camp as S } from "./state.js";
import { api } from "./api.js";
import { $, esc, toast, logLine, aceById, crewPack } from "./render.js";
import { renderCompany } from "./company.js";
import { pullHubState } from "./homecoming.js";
import { renderFoldedChronicle } from "./chronicle.js";

/* ---- camp card: the hearth talks (the camp itself is what stands in the Rock Jungle; no level) ---- */
export function renderCampCard() {
  renderHearthList();
}

/* ---- hearth · support talks ------------------------------------------------------- */
let hearthPending = null;
function aceName(id) {
  const ace = aceById(id);
  if (ace && ace.name) return ace.name;
  const pack = crewPack(id);
  return (pack && pack.name) || id;
}
function hearthEligible() {
  const sw = (state.hub && state.hub.supportWeb) || {};
  let talks = Array.isArray(sw.eligibleTalks) ? sw.eligibleTalks.slice() : [];
  if (!talks.length && window.VA_CAMP_TALKS && Array.isArray(window.VA_CAMP_TALKS.talks)) {
    // Fallback: authored C talks for the sealed company circle
    const circle = new Set(sw.circle || []);
    if (!circle.size) {
      const co = state.hub.company || {};
      ["core", "band", "joinedLater"].forEach(k => (co[k] || []).forEach(x => {
        const id = (x && typeof x === "object") ? (x.id || x.heroId) : x;
        if (id) circle.add(String(id));
      }));
    }
    talks = window.VA_CAMP_TALKS.talks.filter(t => t && t.rank === "C" && circle.has(String(t.a)) && circle.has(String(t.b))).slice(0, 8);
  }
  return talks;
}
function renderHearthList() {
  const listEl = $("hearth-list");
  const stage = $("hearth-stage");
  if (!listEl) return;
  if (stage) stage.classList.remove("show");
  hearthPending = null;
  const talks = hearthEligible();
  if (!talks.length) {
    listEl.innerHTML = `<div class="hearth-empty">No support talks ready in this company circle. Co-deploy pairs on a Drop, or seal a wider band.</div>`;
    return;
  }
  listEl.innerHTML = talks.map(t => `<button type="button" class="hearth-talk" data-talk-id="${esc(t.id)}">
        <div class="ht-title">${esc(t.title || t.id)} <span class="ht-rank">[${esc(t.rank || "C")}]</span></div>
        <div class="ht-meta"><b>${esc(aceName(t.a))}</b> · <b>${esc(aceName(t.b))}</b> · ${esc(t.polarity || "")}${t.authored ? " · hand" : ""}</div>
      </button>`).join("");
  listEl.querySelectorAll(".hearth-talk").forEach(btn => { btn.onclick = () => previewHearthTalk(btn.getAttribute("data-talk-id")); });
}
function findTalkById(tid) {
  const sw = (state.hub && state.hub.supportWeb) || {};
  const fromHub = (sw.eligibleTalks || []).find(t => t && t.id === tid);
  if (fromHub) return fromHub;
  return ((window.VA_CAMP_TALKS && window.VA_CAMP_TALKS.talks) || []).find(t => t && t.id === tid) || null;
}
function previewHearthTalk(tid) {
  const talk = findTalkById(tid);
  if (!talk) return toast("Talk missing", "err");
  hearthPending = talk;
  const stage = $("hearth-stage");
  const title = $("hearth-stage-title");
  const beatsEl = $("hearth-stage-beats");
  if (!stage || !beatsEl) return;
  if (title) title.textContent = `${talk.title || tid} · ${aceName(talk.a)} & ${aceName(talk.b)}`;
  beatsEl.innerHTML = (talk.beats || []).map(b => {
    const who = b.speaker === "narrator" ? "Hearth" : aceName(b.speaker);
    return `<div class="${b.speaker === "narrator" ? "hs-beat narrator" : "hs-beat"}"><span class="who">${esc(who)}</span>${esc(b.line || "")}</div>`;
  }).join("");
  stage.classList.add("show");
}
export async function confirmHearthTalk() {
  if (!hearthPending) return;
  const talk = hearthPending;
  if (state.hostLive) {
    try {
      const { data } = await api.campTalk({ talkId: talk.id, a: talk.a, b: talk.b });
      if (!data.ok) throw new Error(data.error || "camp-talk failed");
      if (data.supportWeb) state.hub.supportWeb = data.supportWeb;
      if (data.aces) state.hub.aces = data.aces;
      toast(`Hearth sealed — ${talk.title}`, "ok");
      logLine(`Support talk ${talk.id} · rank ${talk.rank}`);
      await pullHubState();
      renderHearthList();
      renderCompany();
      return;
    } catch (e) {
      toast("Live talk failed: " + e.message + " — demo seal", "err");
    }
  }
  // Demo / map-only: bump local ace bonds + mark talk done on supportWeb
  state.hub.aces = state.hub.aces || [];
  const delta = 8;
  for (const ace of state.hub.aces) {
    if (!ace || (ace.id !== talk.a && ace.id !== talk.b)) continue;
    ace.bonds = ace.bonds || {};
    const other = ace.id === talk.a ? talk.b : talk.a;
    ace.bonds[other] = (Number(ace.bonds[other]) || 0) + delta;
  }
  state.hub.supportWeb = state.hub.supportWeb || {};
  const pb = state.hub.supportWeb.pairBonds = state.hub.supportWeb.pairBonds || {};
  const pid = talk.pairId || [talk.a, talk.b].sort().join("__");
  const row = pb[pid] || { points: 0, rank: "C", talksDone: [] };
  row.points = (Number(row.points) || 0) + delta;
  row.talksDone = Array.from(new Set([...(row.talksDone || []), talk.id]));
  row.rank = row.points >= 55 ? "A" : row.points >= 25 ? "B" : "C";
  pb[pid] = row;
  state.hub.supportWeb.eligibleTalks = (state.hub.supportWeb.eligibleTalks || []).filter(t => t && t.id !== talk.id);
  toast(`Hearth holds (demo) — ${talk.title}`, "ok");
  logLine(`Demo support talk ${talk.id}`);
  renderHearthList();
  renderCompany();
}
export function cancelHearthTalk() {
  hearthPending = null;
  const stage = $("hearth-stage");
  if (stage) stage.classList.remove("show");
}

/* ---- camp clock panel (the DERIVE faces) ------------------------------------------------ */
export async function refreshCamp() {
  const [camp, intel, chron, exp] = await Promise.allSettled([api.camp(), api.intel(), api.chronicle(), api.exposure()]);
  S.camp = camp.status === "fulfilled" && camp.value.ok ? camp.value.camp : null;
  S.intel = intel.status === "fulfilled" && intel.value.ok ? intel.value.face : null;
  S.chronicle = chron.status === "fulfilled" && chron.value.ok ? chron.value.face : null;
  S.exposure = exp.status === "fulfilled" && exp.value.ok && exp.value.present ? exp.value : null;
  renderFoldedChronicle();
}

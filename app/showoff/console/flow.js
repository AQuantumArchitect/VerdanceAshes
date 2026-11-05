// The sortie flow (owner calls, 2026-11-03/04): once the job is chosen the field loads in BAR behind
// the hub, and the player walks one question per screen:
//
//   talks   What does the company need to say?   every pending talk, each answered (or declined)
//   party   Who's on the drop?                   operations.js renderDropSquad
//   reserve What else do we bring?               the reserve and the mercenary store, one screen
//
// Talks: the story scenes and the company matters the kernel has open (verdance.readings.narrative),
// and one hearth support talk. Every talk has the null answer "No time for this." A declined scene
// or matter is closed for good; a declined support talk can come back (supports build up). Two talks
// at most per drop (TALKS_PER_DROP); whatever is left waits for the next one.
// Talks never change the mission: the field is already loading.
import { state, session } from "./state.js";
import { api } from "./api.js";
import { $, esc, escape, pretty, toast } from "./render.js";
import { hearthEligible, hearthName, sealHearthTalk } from "./home.js";

const NULL_LABEL = "No time for this.";
// At most this many talks before one drop (playtest, 2026-11-04: four in a row on the 20th sortie is
// a chore). Story scenes go first, then the most pressing matter, then a support talk; the rest wait.
export const TALKS_PER_DROP = 2;
let queue = [];            // the talks of this flow, fixed when it opens
let answered = new Map();  // talk key -> the answer's label
let busy = false;

function sceneTalk(s) {
  return {
    key: "scene:" + s.id, kind: "scene", title: s.title,
    who: s.pair.map(pretty), setup: s.setup || "",
    beats: (s.beats || []).map(b => ({ who: pretty(b.speaker), text: b.text })),
    answers: (s.choices || []).map(c => ({ id: c.id, label: c.label, note: c.null ? "changes nothing" : (c.stance || ""), null: !!c.null })),
  };
}
function matterTalk(t) {
  return {
    key: "matter:" + t.id, kind: "matter", title: t.title,
    who: (t.perspectives || []).map(p => pretty(p.speaker)), setup: t.opening || t.reason || "",
    beats: (t.perspectives || []).map(p => ({ who: pretty(p.speaker), text: p.text })),
    answers: (t.choices || []).map(c => ({ id: c.id, label: c.label, note: c.null ? "changes nothing" : (c.obligation || c.stance || ""), null: !!c.null })),
  };
}
function hearthTalk(t) {
  return {
    key: "hearth:" + t.id, kind: "hearth", title: t.title || t.id, talk: t,
    who: [hearthName(t.a), hearthName(t.b)], setup: "",
    beats: (t.beats || []).map(b => ({ who: b.speaker === "narrator" ? "" : hearthName(b.speaker), text: b.line || "" })),
    answers: [{ id: "seal", label: "Sit with them.", note: "their bond grows" }, { id: "none", label: NULL_LABEL, note: "changes nothing", null: true }],
  };
}

// What the camp needs to talk about before this drop.
export function buildTalkQueue() {
  const n = session.narrative || {};
  const scenes = (n.scenes || []).filter(s => (s.choices || []).length).map(sceneTalk);
  // one matter at a time: the company's most pressing open question it hasn't declined
  const matter = (n.threads || []).find(t => t.stage === "Available" && !t.passed && (t.choices || []).length);
  const hearth = (hearthEligible() || [])[0];
  queue = scenes.concat(matter ? [matterTalk(matter)] : [], hearth ? [hearthTalk(hearth)] : []).slice(0, TALKS_PER_DROP);
  answered = new Map();
  return queue;
}
export function talksLeft() { return queue.filter(t => !answered.has(t.key)).length; }
export function hasTalks() { return queue.length > 0; }

export function renderTalks() {
  const root = $("flow-talks");
  if (!root) return;
  const next = queue.find(t => !answered.has(t.key));
  const done = queue.length - talksLeft();
  if (!queue.length) {
    root.innerHTML = `<p class="flow-empty">Nothing the company needs to say this time.</p>`;
    return;
  }
  const said = queue.filter(t => answered.has(t.key)).map(t =>
    `<li><b>${escape(t.title)}</b> <span>${escape(answered.get(t.key))}</span></li>`).join("");
  if (!next) {
    root.innerHTML = `<p class="flow-kicker">${queue.length === 1 ? "Talked through" : queue.length === 2 ? "Both talked through" : `All ${queue.length} talked through`}</p><ul class="flow-said">${said}</ul>`;
    return;
  }
  root.innerHTML =
    `<p class="flow-kicker">Talk ${done + 1} of ${queue.length}${next.who.length ? " · " + escape(next.who.join(" & ")) : ""}</p>` +
    `<h3 class="flow-talk-title">${escape(next.title)}</h3>` +
    (next.setup ? `<p class="flow-setup">${escape(next.setup)}</p>` : "") +
    next.beats.map(b => `<p class="flow-beat">${b.who ? `<b>${escape(b.who)}</b>` : ""}${escape(b.text)}</p>`).join("") +
    `<div class="flow-answers" role="group" aria-label="Your answer">` +
    next.answers.map(a => `<button type="button" class="${a.null ? "null" : ""}" data-talk-answer="${escape(a.id)}" ${busy ? "disabled" : ""}>` +
      `<span>${escape(a.label)}</span>${a.note ? `<small>${escape(a.note)}</small>` : ""}</button>`).join("") +
    `</div>` + (said ? `<ul class="flow-said">${said}</ul>` : "");
  root.querySelectorAll("[data-talk-answer]").forEach(b => { b.onclick = () => answer(next, b.dataset.talkAnswer); });
}

async function answer(talk, answerId) {
  if (busy) return;
  const a = talk.answers.find(x => x.id === answerId);
  if (!a) return;
  busy = true;
  renderTalks();
  try {
    if (talk.kind === "hearth") {
      if (!a.null) await sealHearthTalk(talk.talk);
    } else if (state.hostLive && session.narrative) {
      const { ok, data } = await api.narrativeChoice({ choiceId: a.id, expectedRevision: session.narrative.revision, requestId: crypto.randomUUID() });
      if (!ok || !data.ok) throw new Error((data && data.error) || "The answer could not be recorded.");
      session.narrative = data.narrative;
    }
    answered.set(talk.key, a.null ? "No time" : a.label);
  } catch (e) {
    toast(e.message, "err");
  } finally {
    busy = false;
    renderTalks();
    if (window.Verdance && window.Verdance.onTalksChanged) window.Verdance.onTalksChanged();
  }
}

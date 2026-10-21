// Home: the camp card (raise the shelf), the camp clock panel (the DERIVE faces the kernel
// serves: /api/camp, /api/intel, /api/exposure, /api/chronicle) and the hearth talks.
//
// Law: the hub shows INTEL, never truth. Zone rows come from the company's own belief frame
// (value/confidence/age/source). "dark" means nobody has looked. /api/exposure is our side of
// the mirror only; /api/divergence and /api/truth are dev faces the kernel refuses to the player.
import { state, camp as S, commerce, metalKOf, prettyMap } from "./state.js";
import { api } from "./api.js";
import { $, esc, toast, logLine, aceById, crewPack } from "./render.js";
import { renderBoard, renderMapPicker, focusMapAndRepaint } from "./board.js";
import { onChoice, refreshTheaterForFocus } from "./operations.js";
import { renderCompany } from "./company.js";
import { renderBadges, renderHeadline } from "./shell.js";
import { pullHubState } from "./homecoming.js";
import { renderFoldedChronicle } from "./chronicle.js";

/* ---- camp card ----------------------------------------------------------------- */
export function renderCampCard() {
  const camp = state.hub.homeCamp || {};
  const c = commerce();
  const level = Number(camp.level || 0);
  const cleared = !!(camp.cleared || (state.hub.flags && state.hub.flags.homeCleared));
  const ready = !!(camp.clearReady || (state.hub.flags && state.hub.flags.homeClearReady));
  const tCost = Number(camp.raiseTnbCost != null ? camp.raiseTnbCost : 1);
  const mCost = Number(camp.raiseMetalCostK != null ? camp.raiseMetalCostK : 1);
  const canRaise = camp.canRaise != null ? !!camp.canRaise : (!cleared && Number(c.tenebrium || 0) >= tCost && metalKOf(c) >= mCost);
  if ($("camp-sheet-stats")) {
    $("camp-sheet-stats").innerHTML =
      `<span class="chip">L${level}</span>` +
      `<span class="chip">${esc(prettyMap(camp.mapId || state.hub.sessionHomeMap || "the_rock_jungle"))}</span>` +
      `<span class="chip">${Number(c.tenebrium || 0)} Tnb</span>` +
      `<span class="chip">${(metalKOf(c) * 1000).toLocaleString()} metal</span>` +
      (cleared ? `<span class="chip">cleared</span>` : "") +
      (ready && !cleared ? `<span class="chip">clear-ready</span>` : "") +
      (camp.commanderLine != null ? `<span class="chip">${camp.commanderUnlocked ? "command walker" : "walker scrap"}</span>` : "");
  }
  const raiseBtn = $("btn-camp-raise");
  if (raiseBtn) {
    raiseBtn.hidden = !!cleared;
    raiseBtn.disabled = !canRaise;
    raiseBtn.textContent = canRaise
      ? `Raise camp (L${level} → L${level + 1}) · ${tCost} Tnb + ${(mCost * 1000).toLocaleString()} metal`
      : `Need ${tCost} Tnb + ${(mCost * 1000).toLocaleString()} metal to raise`;
  }
  renderHearthList();
}

export async function doHomeBuild() {
  if (state.hostLive) {
    try {
      toast("Raising the jungle camp…");
      const { ok, data } = await api.homeBuild();
      if (!ok || data.ok === false) return toast((data && data.error) || "Camp build failed", "err");
      if (data.homeCamp) state.hub.homeCamp = data.homeCamp;
      if (data.flags) state.hub.flags = Object.assign(state.hub.flags || {}, data.flags);
      if (data.tenebrium != null) {
        state.hub.tenebrium = data.tenebrium;
        if (state.hub.commerce) state.hub.commerce.tenebrium = data.tenebrium;
      }
      if (data.commerce) state.hub.commerce = data.commerce;
      logLine(`Jungle camp raised to L${(data.homeCamp && data.homeCamp.level) || "?"}.`);
      toast("Camp raised — scale at home", "ok");
      await pullHubState();
      refreshTheaterForFocus();
      return;
    } catch (e) {
      return toast(String(e.message || e), "err");
    }
  }
  // Map-only demo bag
  const c = commerce();
  const tnb = Number(c.tenebrium || 0);
  const mk = metalKOf(c);
  if (tnb < 1) return toast("Need 1 Tenebrium — raid to print", "err");
  if (mk < 1) return toast("Need 1,000 campaign metal", "err");
  c.tenebrium = tnb - 1;
  c.metalK = mk - 1;
  delete c.scrapCredits;
  delete c.credits;
  state.hub.homeCamp = state.hub.homeCamp || { level: 0, mapId: "the_rock_jungle" };
  state.hub.homeCamp.level = (state.hub.homeCamp.level || 0) + 1;
  state.hub.flags = state.hub.flags || {};
  if (state.hub.homeCamp.level >= 1 || c.tenebrium >= 3) state.hub.flags.homeClearReady = true;
  state.hub.tenebrium = c.tenebrium;
  logLine(`Demo camp → L${state.hub.homeCamp.level}`);
  toast("Camp raised (demo bag)", "ok");
  renderBadges();
  renderHeadline();
  renderMapPicker();
  renderBoard();
}
export async function raiseCamp() {
  await doHomeBuild();
  renderCampCard();
}
export function openFoundingSortie() {
  const founding = ((state.hub.node || {}).choices || []).find(ch =>
    ch && ch.kind === "deploy" && (
      (ch.effect && ch.effect.journey === "home_founding") ||
      String((ch.effect && ch.effect.mapId) || "") === "the_rock_jungle" ||
      /rock jungle|found/i.test(String(ch.label || ""))
    ));
  if (founding) {
    state.focusMap = "the_rock_jungle";
    onChoice(founding.id);
    return;
  }
  focusMapAndRepaint("the_rock_jungle", "Founding sortie");
  toast("Mark the Rock Jungle founding route, then Drop", "ok");
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
  renderCampPanel();
  renderFoldedChronicle();
}
export function clock(min) {
  const m = Math.max(0, Math.round(Number(min) || 0));
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
  return (d ? d + "d " : "") + String(h).padStart(2, "0") + ":" + String(mm).padStart(2, "0");
}
function zoneRows() {
  // intel/1 nodes -> per zone {label, mapId, ours, held, strength, threat}
  const out = new Map();
  for (const r of (S.intel && S.intel.nodes) || []) {
    if (!r.role || !r.node || String(r.node).startsWith("hero:") || String(r.node).startsWith("company") || String(r.node).startsWith("people")) continue;
    const z = out.get(r.node) || { id: r.node, label: r.label || r.node, mapId: r.mapId };
    z[r.role] = r;
    out.set(r.node, z);
  }
  return [...out.values()];
}
function believed(z) {
  const o = z.ours || {}, h = z.held || {};
  const dark = (o.state === "dark" || o.value == null) && (h.state === "dark" || h.value == null);
  if (dark) return { word: "nobody has looked", cls: "dark", conf: 0 };
  const ov = Number(o.value ?? 0.5), hv = Number(h.value ?? 0.5), oc = Number(o.confidence || 0), hc = Number(h.confidence || 0);
  if (ov > 0.5 && oc > 0.15) return { word: "ours", cls: "ours", conf: oc };
  if (hv > 0.5 && hc > 0.15) return { word: "held by someone", cls: "theirs", conf: hc };
  if (hv <= 0.5 && hc > 0.15) return { word: "empty", cls: "empty", conf: hc };
  return { word: "unsure", cls: "dark", conf: Math.max(oc, hc) };
}
const stateWord = (r) => (r && r.state) || "dark";

function renderCampPanel() {
  const root = $("panel-camp");
  if (!root) return;
  if (!S.camp && !S.intel) {
    root.innerHTML = `<h2>Camp</h2><p class="camp-note">No camp face yet. Bring the first sortie home and the clock starts.</p>`;
    return;
  }
  const camp = S.camp || {};
  const counts = { current: camp.known, stale: camp.stale, dark: camp.dark };
  const q = (camp.questions && camp.questions.length ? camp.questions : (S.intel && S.intel.questions)) || [];
  const rows = zoneRows();
  const maps = [...new Set(rows.map(z => z.mapId).filter(Boolean))].sort();
  if (!S.mapFilter || !maps.includes(S.mapFilter)) {
    const focus = state.focusMap;
    const lit = (m) => rows.filter(z => z.mapId === m && believed(z).cls !== "dark").length;
    S.mapFilter = (camp.homeMapId && maps.includes(camp.homeMapId)) ? camp.homeMapId
      : (focus && maps.includes(focus)) ? focus
      : (maps.slice().sort((a, b) => lit(b) - lit(a))[0] || null);
  }
  const shown = rows.filter(z => !S.mapFilter || z.mapId === S.mapFilter).sort((a, b) => String(a.label).localeCompare(String(b.label)));
  const heroes = (Array.isArray(camp.people) ? camp.people : Object.entries(camp.people || {}).map(([heroId, rec]) => ({ heroId, ...(rec || {}) }))).map(h => ({ ...h, hid: h.heroId || h.hid }));
  const atCamp = heroes.filter(h => (h.where || "camp") === "camp" && h.status !== "dead" && h.inCompany !== false);
  const away = heroes.filter(h => h.where === "posted" || h.where === "transit" || (h.where === "field" && h.status !== "dead"));
  const pend = S.exposure && S.exposure.pending;
  const crossed = S.exposure && S.exposure.factions && S.exposure.factions.armada;
  const surprise = (S.intel && S.intel.surprise) || null;
  const pauses = (camp.pauses || []).slice(-6).reverse();
  const dis = S.busy ? "disabled" : "";

  root.innerHTML = `
    <h2>Camp</h2>
    <div class="camp-clock">
      <div><span class="cc-big">${esc(clock(camp.clockMinutes ?? (S.intel && S.intel.as_of_minute)))}</span><span class="cc-sub">since the first Drop</span></div>
      <div class="cc-counts">
        <span class="badge good" title="zones we have looked at within 12h">known ${esc(counts.current ?? counts.known ?? "–")}</span>
        <span class="badge warn" title="looked at once, stale now">stale ${esc(counts.stale ?? "–")}</span>
        <span class="badge" title="nobody has looked">dark ${esc(counts.dark ?? "–")}</span>
      </div>
    </div>
    <p class="camp-note">The map shows what the company <em>believes</em>. Looking costs hours; nobody tells you what you did not go and see.</p>

    <h3>Run the clock</h3>
    <div class="camp-actions">
      <button type="button" class="btn-ghost" data-act="rest" data-hours="8" ${dis}>Rest 8h</button>
      <button type="button" class="btn-ghost" data-act="rest" data-hours="24" ${dis}>Rest a day</button>
      <button type="button" class="btn-ghost" data-act="wait" data-hours="4" ${dis}>Wait 4h</button>
    </div>
    <div class="camp-actions camp-row">
      <select id="camp-zone-pick" ${dis}>
        <option value="">— pick a zone —</option>
        ${shown.map(z => `<option value="${esc(z.id)}" ${S.zonePick === z.id ? "selected" : ""}>${esc(z.label)}</option>`).join("")}
      </select>
      <button type="button" class="btn-ghost" data-act="scout" ${dis} title="A patrol goes and looks (≈4h + travel). Hostile ground may cost the patrol.">Scout</button>
      <select id="camp-hero-pick" ${dis}>
        <option value="">— who —</option>
        ${atCamp.map(h => `<option value="${esc(h.hid)}" ${S.heroPick === h.hid ? "selected" : ""}>${esc(h.name || h.hid)}</option>`).join("")}
      </select>
      <button type="button" class="btn-ghost" data-act="post" ${dis} title="Post someone on a zone: they keep looking (and risk a wound on hostile ground). Posted people do not board the Drop.">Post</button>
    </div>
    ${S.busy ? `<p class="camp-note camp-busy">the clock is running…</p>` : ""}

    ${away.length ? `<h3>Away from camp</h3><div class="camp-people">${away.map(h => `
      <div class="camp-person">
        <span>${esc(h.name || h.hid)}</span>
        <span class="muted">${esc(h.where === "transit" ? ("on the road → " + (h.then === "camp" ? "camp" : (h.label || h.zoneId || "?")) + " · back " + clock(h.eta)) : (h.where === "field" ? ("left in the field at " + (h.label || h.zoneId || "?")) : ("posted on " + (h.label || h.zoneId || "?"))))}${h.wounded ? " · wounded" : ""}</span>
        <button type="button" class="btn-ghost tiny" data-act="recall" data-hero="${esc(h.hid)}" ${S.busy || h.where === "transit" ? "disabled" : ""}>Recall</button>
      </div>`).join("")}</div>` : ""}

    ${pauses.length ? `<h3>What the clock said</h3><ul class="camp-pauses">${pauses.map(p => `<li><span class="muted">${esc(clock(p.minute))}</span> ${esc(p.witness || p.pause)}</li>`).join("")}</ul>` : ""}

    ${surprise && surprise.top && surprise.top.length ? `<h3>Last homecoming: what the ground said</h3>
      <ul class="camp-pauses">${surprise.top.slice(0, 3).map(t => `<li><strong>${esc(t.label || t.zoneId)}</strong>: believed ${esc(t.believed)}, found ${esc(t.found)} <span class="muted">(${(Number(t.surprise) || 0).toFixed(2)}${t.eta != null ? ", looked " + Math.round(Number(t.eta) * 100) + "%" : ""})</span></li>`).join("")}</ul>` : ""}

    <h3>The open questions</h3>
    <div class="camp-questions">${q.map(x => `<div class="camp-q"><span class="q-icon">${esc(x.icon || "?")}</span><span>${esc(x.question || x.text || x.id)}</span><span class="badge ${x.status === "settled" ? "gold" : (x.status === "torn" ? "warn" : "")}">${esc(x.status || "open")}${x.lean ? " · " + esc(x.lean) : ""}</span></div>`).join("") || `<p class="camp-note">no questions yet</p>`}</div>

    <h3>What we believe <span class="muted">(${esc(S.mapFilter || "all")})</span></h3>
    ${maps.length > 1 ? `<div class="camp-actions">${maps.map(m => `<button type="button" class="btn-ghost tiny ${m === S.mapFilter ? "on" : ""}" data-map="${esc(m)}">${esc(m.replace(/_/g, " "))}</button>`).join("")}</div>` : ""}
    <table class="camp-zones"><thead><tr><th>zone</th><th>belief</th><th>sure</th><th>last looked</th></tr></thead><tbody>
      ${shown.map(z => { const b = believed(z); const o = z.ours || z.held || {}; return `<tr class="bz-${b.cls}" data-zone="${esc(z.id)}">
        <td>${esc(z.label)}</td><td>${esc(b.word)}</td><td>${Math.round(b.conf * 100)}%</td>
        <td class="muted">${esc(stateWord(o) === "dark" ? "never" : (o.age_min != null ? clock(o.age_min) + " ago" : stateWord(o)))}${o.source ? " · " + esc(String(o.source).split(":")[0]) : ""}</td></tr>`; }).join("")}
    </tbody></table>

    ${crossed ? `<h3>What they know of us</h3><p class="camp-note">Armada has eyes on ${esc((crossed.known || []).length)} of the ${esc(crossed.ofOurs)} zones we believe are ours, suspects ${esc((crossed.suspected || []).length)}, is blind to ${esc((crossed.blind || []).length)}.${pend && pend.queued ? " <em>(their picture is still catching up)</em>" : ""}</p>` : ""}
  `;
  root.querySelectorAll("[data-act]").forEach(b => b.onclick = () => campAct(b.dataset.act, b));
  root.querySelectorAll("[data-map]").forEach(b => b.onclick = () => { S.mapFilter = b.dataset.map; renderCampPanel(); });
  const zp = $("camp-zone-pick"); if (zp) zp.onchange = () => { S.zonePick = zp.value || null; };
  const hp = $("camp-hero-pick"); if (hp) hp.onchange = () => { S.heroPick = hp.value || null; };
  root.querySelectorAll("tr[data-zone]").forEach(tr => tr.onclick = () => { S.zonePick = tr.dataset.zone; const sel = $("camp-zone-pick"); if (sel) sel.value = S.zonePick; });
}

async function campAct(action, btn) {
  if (S.busy) return;
  const body = { action };
  if (action === "rest" || action === "wait") body.hours = Number(btn.dataset.hours || 8);
  if (action === "scout") { if (!S.zonePick) { toast("Pick a zone to scout", "err"); return; } body.zoneId = S.zonePick; }
  if (action === "post") { if (!S.zonePick || !S.heroPick) { toast("Pick who and where", "err"); return; } body.zoneId = S.zonePick; body.heroId = S.heroPick; }
  if (action === "recall") body.heroId = btn.dataset.hero;
  S.busy = true;
  renderCampPanel();
  try {
    const { data: j } = await api.campAct(body);
    if (!j.ok) throw new Error(j.error || "camp action failed");
    const p = (j.pauses || []).slice(-1)[0];
    if (j.scouted) toast(`Patrol: ${j.scouted.label} is ${j.scouted.found}` + (j.scouted.surprise > 0.3 ? ` (we believed ${j.scouted.believed})` : ""), j.scouted.surprise > 0.3 ? "err" : "ok");
    else if (p && p.witness) toast(p.witness, p.pause === "casualty" ? "err" : "ok");
    else if (j.healed && j.healed.length) toast(`${j.healed.length} back on their feet`, "ok");
    else toast(`${Math.round((j.elapsedMinutes || 0) / 60)}h passed`, "ok");
  } catch (e) {
    toast("Camp: " + e.message, "err");
  } finally {
    S.busy = false;
    await refreshCamp();
    try { await pullHubState(); } catch (_) { /* host down */ }
  }
}

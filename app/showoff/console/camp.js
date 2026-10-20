// Camp tab: the interstitial layer (passes two..four). Self-contained: reads the DERIVE faces the
// kernel serves (/api/camp, /api/intel, /api/chronicle, /api/divergence) and runs the clock through
// POST /api/camp-act. Nothing here touches campaign.js state; the hub re-pulls after an action.
//
// Law: the hub shows INTEL, never truth. Zone rows come from the company's own belief frame
// (value/confidence/age/source). "dark" means nobody has looked.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const api = (p) => (window.Verdance && typeof window.Verdance.api === "function") ? window.Verdance.api(p) : p;
const notify = (m, k) => { try { window.Verdance && window.Verdance.notify && window.Verdance.notify(m, k); } catch (_) {} };

const S = { camp: null, intel: null, chronicle: null, divergence: null, busy: false, mapFilter: null, heroPick: null, zonePick: null };

async function getJson(path) {
  const r = await fetch(api(path), { cache: "no-store" });
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

export async function refreshCamp() {
  const [camp, intel, chron, div] = await Promise.allSettled([
    getJson("/api/camp"), getJson("/api/intel"), getJson("/api/chronicle"), getJson("/api/divergence"),
  ]);
  S.camp = camp.status === "fulfilled" && camp.value.ok ? camp.value.camp : null;
  S.intel = intel.status === "fulfilled" && intel.value.ok ? intel.value.face : null;
  S.chronicle = chron.status === "fulfilled" && chron.value.ok ? chron.value.face : null;
  S.divergence = div.status === "fulfilled" && div.value.ok ? div.value : null;
  render();
}

function clock(min) {
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

function stateWord(r) {
  if (!r) return "dark";
  return r.state || "dark";
}

function render() {
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
    let focus = null;
    try { focus = window.Verdance && window.Verdance.snapshot && window.Verdance.snapshot().focusMap; } catch (_) {}
    const lit = (m) => rows.filter(z => z.mapId === m && believed(z).cls !== "dark").length;
    S.mapFilter = (camp.homeMapId && maps.includes(camp.homeMapId)) ? camp.homeMapId
      : (focus && maps.includes(focus)) ? focus
      : (maps.slice().sort((a, b) => lit(b) - lit(a))[0] || null);
  }
  const shown = rows.filter(z => !S.mapFilter || z.mapId === S.mapFilter).sort((a, b) => String(a.label).localeCompare(String(b.label)));
  const heroes = (Array.isArray(camp.people) ? camp.people : Object.entries(camp.people || {}).map(([heroId, rec]) => ({ heroId, ...(rec || {}) }))).map(h => ({ ...h, hid: h.heroId || h.hid }));
  const atCamp = heroes.filter(h => (h.where || "camp") === "camp" && h.status !== "dead" && h.inCompany !== false);
  const away = heroes.filter(h => h.where === "posted" || h.where === "transit");
  const div = S.divergence && S.divergence.face;
  const pend = S.divergence && S.divergence.pending;
  const crossed = div && div.crossed && div.crossed.armada && div.crossed.armada.aboutCompany;
  const surprise = (S.intel && S.intel.surprise) || null;
  const pauses = (camp.pauses || []).slice(-6).reverse();

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
      <button type="button" class="btn-ghost" data-act="rest" data-hours="8" ${S.busy ? "disabled" : ""}>Rest 8h</button>
      <button type="button" class="btn-ghost" data-act="rest" data-hours="24" ${S.busy ? "disabled" : ""}>Rest a day</button>
      <button type="button" class="btn-ghost" data-act="wait" data-hours="4" ${S.busy ? "disabled" : ""}>Wait 4h</button>
    </div>
    <div class="camp-actions camp-row">
      <select id="camp-zone-pick" ${S.busy ? "disabled" : ""}>
        <option value="">— pick a zone —</option>
        ${shown.map(z => `<option value="${esc(z.id)}" ${S.zonePick === z.id ? "selected" : ""}>${esc(z.label)}</option>`).join("")}
      </select>
      <button type="button" class="btn-ghost" data-act="scout" ${S.busy ? "disabled" : ""} title="A patrol goes and looks (≈4h + travel). Hostile ground may cost the patrol.">Scout</button>
      <select id="camp-hero-pick" ${S.busy ? "disabled" : ""}>
        <option value="">— who —</option>
        ${atCamp.map(h => `<option value="${esc(h.hid)}" ${S.heroPick === h.hid ? "selected" : ""}>${esc(h.name || h.hid)}</option>`).join("")}
      </select>
      <button type="button" class="btn-ghost" data-act="post" ${S.busy ? "disabled" : ""} title="Post someone on a zone: they keep looking (and risk a wound on hostile ground). Posted people do not board the Drop.">Post</button>
    </div>
    ${S.busy ? `<p class="camp-note camp-busy">the clock is running…</p>` : ""}

    ${away.length ? `<h3>Away from camp</h3><div class="camp-people">${away.map(h => `
      <div class="camp-person">
        <span>${esc(h.name || h.hid)}</span>
        <span class="muted">${esc(h.where === "transit" ? ("on the road → " + (h.then === "camp" ? "camp" : (h.label || h.zoneId || "?")) + " · back " + clock(h.eta)) : ("posted on " + (h.label || h.zoneId || "?")))}${h.wounded ? " · wounded" : ""}</span>
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

    ${crossed ? `<h3>What they know of us</h3><p class="camp-note">Armada has eyes on ${esc(crossed.known.length)} of our ${esc(crossed.ofOurs)} holdings, suspects ${esc(crossed.suspected.length)}, is blind to ${esc(crossed.blind.length)}.${pend && pend.queued ? " <em>(their picture is still catching up)</em>" : ""}</p>` : ""}

    ${S.chronicle && !$("panel-camp-chronicle") ? `<h3>The chronicle</h3><div class="camp-chronicle">${renderChronicle(S.chronicle)}</div>` : ""}
  `;
  const cp = $("panel-camp-chronicle");
  if (cp) cp.innerHTML = S.chronicle ? `<h2>The folded record</h2><p class="camp-note">Drops under one reading fold into a chapter; named events never fold; what is still owed stays listed until a later push answers it.</p>${renderChronicle(S.chronicle)}` : "";
  root.querySelectorAll("[data-act]").forEach(b => b.onclick = () => act(b.dataset.act, b));
  root.querySelectorAll("[data-map]").forEach(b => b.onclick = () => { S.mapFilter = b.dataset.map; render(); });
  const zp = $("camp-zone-pick"); if (zp) zp.onchange = () => { S.zonePick = zp.value || null; };
  const hp = $("camp-hero-pick"); if (hp) hp.onchange = () => { S.heroPick = hp.value || null; };
  root.querySelectorAll("tr[data-zone]").forEach(tr => tr.onclick = () => { S.zonePick = tr.dataset.zone; const sel = $("camp-zone-pick"); if (sel) sel.value = S.zonePick; });
}

function renderChronicle(c) {
  // verdance-chronicle/0.1: rows are chapter folds (fold + keeps) or single kept events
  const rows = c.rows || [];
  const li = rows.slice(-6).map(r => {
    const f = r.fold;
    if (f && f.kind === "chapter") {
      const v = f.verdicts || {};
      const head = `${esc(r.icon || "")} <strong>${esc(String(f.attractor || "").replace(/_/g, " "))}</strong>: ${esc(f.n)} Drop${f.n === 1 ? "" : "s"} (m${esc((f.missions || [])[0])}–m${esc((f.missions || []).slice(-1)[0])}) · ${esc(v.victory || 0)}W ${esc(v.partial || 0)}P ${esc(v.defeat || 0)}L${f.dead ? ` · ${esc(f.dead)} dead` : ""}`;
      const keeps = (r.keeps || []).slice(-5).map(k => `<li class="muted">${esc(k.icon || k.token || "")} ${esc(k.text)}</li>`).join("");
      return `<li>${head}${keeps ? `<ul class="camp-pauses camp-keeps">${keeps}</ul>` : ""}</li>`;
    }
    return `<li>${esc(r.icon || r.token || "")} ${esc(r.text || r.id)}</li>`;
  }).join("");
  const owed = (c.open_obligations || []).flatMap(o => typeof o === "string" ? [o] : (o.obligations || [o.text || ""])).filter(Boolean).map(t => `<li>${esc(t)}</li>`).join("");
  const names = new Map((Array.isArray(S.camp && S.camp.people) ? S.camp.people : []).map(h => [h.heroId, h.name]));
  const roll = (c.roll || []).map(r => { const id = typeof r === "string" ? r : (r.heroId || ""); return esc((typeof r === "object" && r.name) || names.get(id) || id); }).filter(Boolean).join(", ");
  return `<ul class="camp-pauses">${li || "<li class=muted>nothing folded yet</li>"}</ul>${roll ? `<p class="camp-note"><strong>On the roll:</strong> ${roll}</p>` : ""}${owed ? `<p class="camp-note"><strong>Still owed</strong></p><ul class="camp-pauses">${owed}</ul>` : ""}`;
}

async function act(action, btn) {
  if (S.busy) return;
  const body = { action };
  if (action === "rest" || action === "wait") body.hours = Number(btn.dataset.hours || 8);
  if (action === "scout") { if (!S.zonePick) { notify("Pick a zone to scout", "err"); return; } body.zoneId = S.zonePick; }
  if (action === "post") { if (!S.zonePick || !S.heroPick) { notify("Pick who and where", "err"); return; } body.zoneId = S.zonePick; body.heroId = S.heroPick; }
  if (action === "recall") body.heroId = btn.dataset.hero;
  S.busy = true; render();
  try {
    const r = await fetch(api("/api/camp-act"), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || "camp action failed");
    const p = (j.pauses || []).slice(-1)[0];
    if (j.scouted) notify(`Patrol: ${j.scouted.label} is ${j.scouted.found}` + (j.scouted.surprise > 0.3 ? ` (we believed ${j.scouted.believed})` : ""), j.scouted.surprise > 0.3 ? "err" : "ok");
    else if (p && p.witness) notify(p.witness, p.pause === "casualty" ? "err" : "ok");
    else if (j.healed && j.healed.length) notify(`${j.healed.length} back on their feet`, "ok");
    else notify(`${Math.round((j.elapsedMinutes || 0) / 60)}h passed`, "ok");
  } catch (e) {
    notify("Camp: " + e.message, "err");
  } finally {
    S.busy = false;
    await refreshCamp();
    try { window.Verdance && window.Verdance.refresh && window.Verdance.refresh(); } catch (_) {}
  }
}

function mount() {
  // Command console (console/workspaces.js): the camp lives in the "home" workspace, the dance
  // chronicle under "chronicle". Legacy tabs layout: a fourth right-column tab. Either way the
  // panel element is #panel-camp and render() owns its contents.
  const home = $("workspace-home");
  const panel = document.createElement("div");
  panel.id = "panel-camp";
  if (home) {
    panel.className = "camp-panel";
    home.appendChild(panel);
    const chron = $("workspace-chronicle");
    if (chron) {
      const d = document.createElement("div");
      d.id = "panel-camp-chronicle"; d.className = "camp-panel";
      chron.appendChild(d);
    }
    document.addEventListener("click", (e) => {
      const b = e.target.closest && e.target.closest("[data-workspace]");
      if (b && (b.dataset.workspace === "home" || b.dataset.workspace === "chronicle")) setTimeout(refreshCamp, 0);
    }, true);
    const camp = $("camp-chip");
    if (camp) camp.addEventListener("click", () => setTimeout(refreshCamp, 0));
  } else {
    const tabs = document.querySelector(".tabs");
    const right = $("col-right");
    if (!tabs || !right || $("tab-camp")) return;
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "tab"; btn.dataset.tab = "camp"; btn.id = "tab-camp"; btn.textContent = "Camp";
    tabs.appendChild(btn);
    panel.hidden = true;
    right.appendChild(panel);
    const all = () => document.querySelectorAll(".tab");
    btn.addEventListener("click", () => {
      all().forEach(t => t.classList.toggle("active", t === btn));
      ["shop", "theaters", "manifold"].forEach(n => { const p = $("panel-" + n); if (p) p.hidden = true; });
      panel.hidden = false;
      refreshCamp();
    });
    all().forEach(t => { if (t !== btn) t.addEventListener("click", () => { panel.hidden = true; }); });
  }
  const css = document.createElement("style");
  css.textContent = `
    .camp-panel{margin-top:.9rem}
    .camp-panel h2{margin:.6rem 0 .2rem}
    .camp-note{font-size:.72rem;color:var(--muted);margin:.2rem 0 .5rem;line-height:1.4}
    .camp-busy{color:var(--steam)}
    .camp-clock{display:flex;justify-content:space-between;align-items:flex-end;gap:.5rem;margin:.2rem 0 .3rem;max-width:40rem}
    .cc-big{font-size:1.25rem;color:var(--gold);font-weight:600;letter-spacing:.02em}
    .cc-sub{display:block;font-size:.62rem;color:var(--muted)}
    .cc-counts{display:flex;gap:.3rem;flex-wrap:wrap}
    .camp-actions{display:flex;gap:.3rem;flex-wrap:wrap;margin:.25rem 0;align-items:center}
    .camp-actions select{background:rgba(0,0,0,.35);color:var(--ink);border:1px solid rgba(61,143,85,.35);border-radius:.3rem;font-size:.72rem;padding:.25rem .35rem;max-width:13rem}
    .btn-ghost.tiny{font-size:.62rem;padding:.15rem .4rem}
    .btn-ghost.on{color:var(--gold);border-color:rgba(212,196,154,.5)}
    .camp-people .camp-person{display:flex;gap:.4rem;align-items:center;justify-content:space-between;font-size:.72rem;padding:.15rem 0;border-bottom:1px solid rgba(61,143,85,.15);max-width:40rem}
    .camp-pauses{list-style:none;margin:.2rem 0;padding:0;font-size:.72rem;line-height:1.45;max-width:46rem}
    .camp-pauses li{padding:.1rem 0;border-bottom:1px solid rgba(61,143,85,.12)}
    .camp-keeps{margin:.1rem 0 .2rem .8rem}
    .camp-questions .camp-q{display:grid;grid-template-columns:1.2rem 1fr auto;gap:.35rem;align-items:center;font-size:.72rem;padding:.15rem 0;max-width:40rem}
    .camp-zones{width:100%;max-width:46rem;border-collapse:collapse;font-size:.7rem}
    .camp-zones th{text-align:left;color:var(--muted);font-weight:500;padding:.15rem .2rem;border-bottom:1px solid rgba(61,143,85,.3)}
    .camp-zones td{padding:.15rem .2rem;border-bottom:1px solid rgba(61,143,85,.12);cursor:pointer}
    .camp-zones tr.bz-ours td:nth-child(2){color:var(--good)}
    .camp-zones tr.bz-theirs td:nth-child(2){color:var(--warn)}
    .camp-zones tr.bz-empty td:nth-child(2){color:var(--ink)}
    .camp-zones tr.bz-dark td:nth-child(2){color:var(--muted);font-style:italic}
    .camp-panel .muted{color:var(--muted)}
  `;
  document.head.appendChild(css);
}

mount();
refreshCamp();
window.VerdanceCamp = { refresh: refreshCamp, state: S };

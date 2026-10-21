// Chronicle: the narrative record of returns (from /api/narrative) and the folded camp
// chronicle (verdance-chronicle/0.1 from /api/chronicle). Readings are the kernel's; the hub
// only lays them out.
import { camp as S } from "./state.js";
import { $, esc, escape, pretty, chronicle } from "./render.js";

// Narrative chronicle + the "last return" card above the theater.
export function renderChronicle(n) {
  $("cc-chronicle").innerHTML = chronicle(n?.chronicle || []);
  const returnCard = $("cc-return");
  const last = n?.chronicle?.[0];
  returnCard.hidden = !last;
  if (last) returnCard.innerHTML = `<summary>Last return · ${escape(last.title)} · ${escape(pretty(last.mapId))}</summary>${chronicle([last])}`;
}

// The folded record: Drops under one reading fold into a chapter; named events never fold;
// what is still owed stays listed until a later push answers it.
export function renderFoldedChronicle() {
  const cp = $("panel-camp-chronicle");
  if (!cp) return;
  const c = S.chronicle;
  if (!c) { cp.innerHTML = ""; return; }
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
  cp.innerHTML = `<h2>The folded record</h2><p class="camp-note">Drops under one reading fold into a chapter; named events never fold; what is still owed stays listed until a later push answers it.</p>` +
    `<ul class="camp-pauses">${li || "<li class=muted>nothing folded yet</li>"}</ul>` +
    (roll ? `<p class="camp-note"><strong>On the roll:</strong> ${roll}</p>` : "") +
    (owed ? `<p class="camp-note"><strong>Still owed</strong></p><ul class="camp-pauses">${owed}</ul>` : "");
}

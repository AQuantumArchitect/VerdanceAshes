// Every fetch in the hub, in one place. The routes here are the ones the kernel serves
// today (tools/verdance_kernel/server.py) — nothing else is called from the page.
import { state } from "./state.js";

export function url(path) { return (state.hostBase || "") + path; }

async function call(path, init) {
  const res = await fetch(url(path), init);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}
const get = (path) => call(path, { cache: "no-store" });
const post = (path, body) => call(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

// Fetch that throws on a non-ok / non-JSON answer (camp faces + narrative use this shape).
export async function getJson(path) {
  const r = await fetch(url(path), { cache: "no-store" });
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

export const api = {
  // GET faces
  status: () => get("/api/status"),
  session: () => get("/api/session"),
  live: () => getJson("/api/live"),
  hubState: () => get("/api/hub-state"),
  result: () => get("/api/result"),
  health: () => get("/api/health"),
  saves: () => get("/api/saves"),
  narrative: () => getJson("/api/narrative"),
  camp: () => getJson("/api/camp"),
  intel: () => getJson("/api/intel"),
  chronicle: () => getJson("/api/chronicle"),
  exposure: () => getJson("/api/exposure"),
  // POST acts
  narrativeChoice: (body) => post("/api/narrative-choice", body),
  campAct: (body) => post("/api/camp-act", body),
  campTalk: (body) => post("/api/camp-talk", body),
  sealCompany: (band) => post("/api/seal-company", { band }),
  // Hot drop: load the field on sortie pick, then drop the chosen packs into the running game.
  preload: (plan) => post("/api/preload", plan),
  drop: (body) => post("/api/drop", body),
  cancelPreload: () => post("/api/cancel-preload"),
  purchase: (listingId) => post("/api/purchase", { listingId }),
  homeBuild: () => call("/api/home-build", { method: "POST" }),
  advanceExtract: () => call("/api/advance?extract=1", { method: "POST" }),
  abandon: () => post("/api/abandon", { reason: "player_abandon" }),
  resetCampaign: () => post("/api/reset-campaign", { confirm: "YES" }),
  saveCampaign: (slot) => post("/api/save-campaign", { slot, label: slot }),
  loadCampaign: (slot) => post("/api/load-campaign", { slot, confirm: "YES" }),
  rebuildHub: () => call("/api/rebuild-hub", { method: "POST" }),
  feedbackBundle: (notes) => post("/api/feedback-bundle", { notes }),
};

// Host probe: same origin first, then the kernel's default port. Returns the live base or null.
export async function probeKernel() {
  const candidates = [];
  if (location.protocol === "http:" || location.protocol === "https:") candidates.push("");
  candidates.push("http://127.0.0.1:8770");
  for (const base of candidates) {
    try {
      const res = await fetch(base + "/api/status", { cache: "no-store" });
      if (!res.ok) continue;
      const data = await res.json();
      if (!(data.schemaVersion && String(data.schemaVersion).indexOf("hub-host") >= 0) &&
          !(data.capabilities && data.capabilities.stamp)) continue;
      return { base, data };
    } catch (_) { /* try next */ }
  }
  return null;
}

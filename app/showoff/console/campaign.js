(function () {
  const H = window.HUB_STATE || {};
  const BOARDS = window.ZONE_BOARDS || {};
  const CREW = window.CREW_PACKS || { core: ["vane","ketha"], heroes: {}, seatCap: 3, startWalletTnb: 5 };
  const state = {
    hub: JSON.parse(JSON.stringify(H)),
    focusMap: null,
    hostLive: false,
    hostBase: "", // "" = same-origin; else http://127.0.0.1:8770
    hostInfo: null,
    markMode: "capture",
    plan: null,
    log: [],
    rhoSel: { i: 0, j: 0 },
    lastResultAt: null,
    crewBand: [], // preamble picks; after seal = who drops (at-base = owned − this)
    dropping: false, // true while /api/deploy is in flight
    warm: { phase: "idle", locked: false, timer: null, poll: null, startedAt: 0 },
    selectedZoneId: null, // last marked / clicked theater zone (recruit tease)
    sortieSynced: false, // after seal, keep local Dropping↔Base picks across hub pulls
    knownCompanyIds: null, // sealed members already sorted Dropping↔Base (absorb new joins)
  };

  function companySurface() {
    return (state.hub && state.hub.company) || {};
  }
  function companySealed() {
    const c = companySurface();
    return !!(c.sealed || (state.hub && state.hub.flags && state.hub.flags.companySealed));
  }
  function crewSeatCap() {
    const c = companySurface();
    return Number(c.seatCap) || Number(CREW.seatCap) || 3;
  }
  function crewWallet() {
    // Prefer live commerce bag (post-sortie SoT). formationWallet* mirrors it
    // on hub rebuild; never let falsy 0 fall through to startWalletTnb (3).
    const bag = (state.hub && state.hub.commerce) || {};
    if (bag.tenebrium != null && bag.tenebrium !== "") return Number(bag.tenebrium) || 0;
    const c = companySurface();
    if (c.formationWalletTnb != null && c.formationWalletTnb !== "") {
      return Number(c.formationWalletTnb) || 0;
    }
    return Number(CREW.startWalletTnb) || 3;
  }
  function crewMetalK() {
    const bag = (state.hub && state.hub.commerce) || {};
    if (bag.metalK != null && bag.metalK !== "") return Number(bag.metalK) || 0;
    const c = companySurface();
    if (c.formationWalletKm != null && c.formationWalletKm !== "") {
      return Number(c.formationWalletKm) || 0;
    }
    return Number(CREW.startWalletKm) || 0;
  }
  function crewHireCost(id) {
    const h = (CREW.heroes || {})[id];
    return h ? Number(h.hireTnb) || 0 : 99;
  }
  function crewHireKm(id) {
    const h = (CREW.heroes || {})[id];
    return h ? Number(h.hireKm) || 0 : 0;
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
    if (Number(km) > 0) bits.push(`<span class="hc-cost km">${(Number(km)*1000).toLocaleString()} metal</span>`);
    if (!bits.length && showFree) bits.push(`<span class="hc-cost free">free</span>`);
    return bits.length ? `<div class="hc-cost-row">${bits.join("")}</div>` : "";
  }
  function crewPack(id) {
    return (CREW.heroes || {})[id] || {};
  }
  function crewChassisName(h) {
    const def = h && h.unitDef;
    const ch = (CREW.chassis || {})[def];
    if (ch && ch.label) return ch.label;
    if (!def) return "?";
    return String(def).replace(/^(leg|arm|cor)/, "");
  }
  function crewHeroName(id) {
    const h = crewPack(id);
    if (h && h.name) return h.name;
    const pool = companySurface().pool || [];
    const hit = pool.find(p => p && p.id === id);
    if (hit && hit.name) return hit.name;
    return id;
  }
  function aceById(id) {
    const aces = (state.hub && state.hub.aces) || [];
    return aces.find(a => a && (a.id === id || a.heroId === id)) || null;
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
  /**
   * Shared hero card — used by THE COMPANY (muster + aces), drop confirm,
   * and later join-pick screens. Level sits opposite the name; XP under level.
   * Hire cost is a badge — never buried in flavor text.
   */
  function renderHeroCard(opts) {
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
    const metaBits = [
      o.meta,
      chassis,
      packN > 1 ? `pack ×${packN}` : null,
      escLines || null,
    ].filter(Boolean);
    // Dedupe if caller already passed chassis in meta
    const meta = [...new Set(metaBits)].join(" · ");
    const rawBlurb = o.blurb != null ? o.blurb : (h.blurb || "");
    const blurb = sanitizeHeroBlurb(rawBlurb);
    const showFree = o.showFreeCost != null ? !!o.showFreeCost : !!o.pickable;
    const costHtml = o.hideCost ? "" : renderCostBadges(costTnb, costKm, { showFree });
    const classes = ["hero-card"]
      .concat(o.classes || [])
      .concat(o.compact ? ["compact"] : [])
      .concat(o.panel ? ["panel"] : [])
      .concat(stats.wounds ? ["wounded"] : [])
      .filter(Boolean)
      .join(" ");
    const xpLine = stats.xp != null
      ? `xp ${stats.xp}`
      : (o.xpLabel || "");
    const levelLine = `L${stats.level}`;
    // Sticky peak: career rank (Green/Proven/…). "Runner" is a SPEED tag, not a rank.
    // Legacy "Blooded" read as wounded — display as Proven.
    let peakRaw = String(stats.rank || o.peak || "").trim();
    if (/^blooded$/i.test(peakRaw) || /^bloodied$/i.test(peakRaw)) peakRaw = "Proven";
    if (!peakRaw || /^runner$/i.test(peakRaw)) peakRaw = "Green";
    const peakNorm = peakRaw.toLowerCase().replace(/\s+/g, "");
    const peakClass = peakNorm
      ? `hc-peak peak-${esc(peakNorm)}`
      : "hc-peak peak-green";
    const peakLabel = peakRaw || "Green";
    const packTags = [].concat(h.tags || [], h.traits || []).filter(Boolean);
    const tagLine = packTags.length
      ? packTags.map(t => String(t).replace(/_/g, " ")).join(" · ")
      : "";
    const attrs = [
      o.dataCrew ? `data-crew="${esc(o.dataCrew)}"` : "",
      o.disabled ? "disabled" : "",
      o.type === "button" || o.dataCrew ? `type="button"` : "",
    ].filter(Boolean).join(" ");
    const tagName = (o.type === "button" || o.dataCrew) ? "button" : "div";
    return `<${tagName} class="${classes}" ${attrs}>
      <div class="hc-name">${esc(name)}${esc(tag)}</div>
      <div class="hc-level" title="${esc(peakLabel)}">${esc(levelLine)}</div>
      <div class="${peakClass}" title="Career rank — not a movement perk">${esc(peakLabel)}</div>
      <div class="hc-meta">${esc(meta)}</div>
      <div class="hc-xp">${esc(xpLine)}</div>
      ${tagLine ? `<div class="hc-tags" title="Procedural tags (boost / nerf)">${esc(tagLine)}</div>` : ""}
      ${costHtml}
      <div class="hc-blurb">${esc(blurb)}</div>
    </${tagName}>`;
  }
  function crewSpent() {
    return state.crewBand.reduce((n, id) => n + crewHireCost(id), 0);
  }
  function crewCoreIds() {
    const c = companySurface();
    if (Array.isArray(c.core) && c.core.length) {
      return c.core.map(x => (typeof x === "string" ? x : x.id)).filter(Boolean);
    }
    return Array.isArray(CREW.core) ? CREW.core.slice() : ["vane", "ketha"];
  }
  function crewBandOrder() {
    const c = companySurface();
    let ids;
    if (Array.isArray(c.unlockedIds) && c.unlockedIds.length) ids = c.unlockedIds.slice();
    else if (Array.isArray(c.pool) && c.pool.length) ids = c.pool.map(p => p.id);
    else {
      ids = Object.keys(CREW.heroes || {}).filter(id => {
        const h = CREW.heroes[id];
        return h && h.role === "band";
      });
    }
    return sortHeroGridIds(ids);
  }
  function heroIsEco(id) {
    const h = crewPack(id) || (CREW.heroes && CREW.heroes[id]) || {};
    const tags = h.tags || [];
    const fe = String(h.fieldEffect || "");
    if (fe === "energy" || fe === "build") return true;
    if (tags.includes("eco_lab") || tags.includes("pad_heart") || tags.includes("field_office") || tags.includes("combat_engineer")) return true;
    return id === "hearth" || id === "solarium" || id === "consul" || id === "twitch";
  }
  function sortHeroGridIds(ids) {
    // Eco cluster first, then startXp (premium/green first), then pack cost.
    const catalogOrder = Array.isArray(CREW.bandOrder) ? CREW.bandOrder : [];
    const catalogRank = Object.fromEntries(catalogOrder.map((id, i) => [id, i]));
    return (ids || []).slice().sort((a, b) => {
      const ae = heroIsEco(a) ? 0 : 1;
      const be = heroIsEco(b) ? 0 : 1;
      if (ae !== be) return ae - be;
      const ha = (CREW.heroes && CREW.heroes[a]) || {};
      const hb = (CREW.heroes && CREW.heroes[b]) || {};
      const ax = Number(ha.startXp);
      const bx = Number(hb.startXp);
      const axn = Number.isFinite(ax) ? ax : 0.5;
      const bxn = Number.isFinite(bx) ? bx : 0.5;
      if (axn !== bxn) return axn - bxn;
      const ac = Number(ha.packCombined) || 0;
      const bc = Number(hb.packCombined) || 0;
      if (ac !== bc) return ac - bc;
      const ar = catalogRank[a];
      const br = catalogRank[b];
      if (ar != null && br != null && ar !== br) return ar - br;
      return String(a).localeCompare(String(b));
    });
  }
  function companyOwnedBand() {
    const c = companySurface();
    return list(c.band).concat(list(c.joinedLater));
  }
  function aceById(id) {
    const aces = (state.hub && state.hub.aces) || [];
    return aces.find(a => a && a.id === id) || null;
  }
  function heroIsDeployable(id) {
    // Dead / lost stay on the company roll but do not drop — confirm panel
    // and deploy payload must only list who is actually shipping.
    const ace = aceById(id);
    const st = String((ace && ace.status) || "active").toLowerCase();
    if (st === "dead" || st === "lost") return false;
    if (ace && ace.deployable === false) return false;
    return true;
  }
  function syncCrewFromHub() {
    const c = companySurface();
    if (!c.sealed) return;
    const ownedList = companyOwnedBand().filter(heroIsDeployable);
    const owned = new Set(ownedList);
    // Server Drop stamps company.deployBand (formation band + joinedLater). Prefer that
    // on first paint so The Company matches what BAR actually receives.
    const serverBand = list(c.deployBand).filter(id => owned.has(id) && heroIsDeployable(id));
    if (!state.knownCompanyIds) state.knownCompanyIds = new Set();

    if (!state.sortieSynced) {
      state.crewBand = (serverBand.length ? serverBand : ownedList).slice();
      state.knownCompanyIds = new Set(ownedList);
      state.sortieSynced = true;
      return;
    }

    // Keep local Dropping↔Base picks for people already sorted.
    state.crewBand = state.crewBand.filter(id => owned.has(id) && heroIsDeployable(id));
    // Absorb brand-new company members (field rescues) into Dropping. Without this,
    // Drop ships them via company_deploy_aces while The Company sidebar never lists them
    // under Dropping after a mid-session hub refresh / retrofill.
    for (const id of ownedList) {
      if (!state.knownCompanyIds.has(id)) {
        if (!state.crewBand.includes(id)) state.crewBand.push(id);
        state.knownCompanyIds.add(id);
      }
    }
    for (const id of [...state.knownCompanyIds]) {
      if (!owned.has(id)) state.knownCompanyIds.delete(id);
    }
  }
  function list(xs) { return Array.isArray(xs) ? xs.map(String) : []; }
  function dropRosterSealed() {
    const phase = state.warm && state.warm.phase;
    // Locked on Confirm drop, before the level starts compiling.
    return phase === "loading" || phase === "sealing" || phase === "up";
  }
  function toggleCrew(id) {
    if (dropRosterSealed()) {
      return toast("This company is locked for the drop. Close Recoil to change who ships.", "warn");
    }
    if (crewCoreIds().includes(id)) {
      if (!heroIsDeployable(id)) {
        return toast(`${crewHeroName(id)} is fallen — they are not dropping`, "warn");
      }
      return toast(
        `${crewHeroName(id)} is core — always drops, and does not use a pack seat. ` +
        (companySealed()
          ? "You can bring every other living pack, or click one to leave it at base."
          : `Pick exactly ${crewSeatCap()} other packs.`),
        "ok"
      );
    }
    const sealed = companySealed();
    const owned = new Set(companyOwnedBand());
    const i = state.crewBand.indexOf(id);

    if (sealed) {
      // Post-seal: move between Dropping ↔ At base (company members only).
      if (!owned.has(id)) return toast("Still locked — find them in the field", "err");
      if (!heroIsDeployable(id)) {
        // Keep them out of Dropping if somehow still listed.
        if (i >= 0) state.crewBand.splice(i, 1);
        if (state.plan) state.plan.deployAces = sealedDeployAces();
        renderCompany();
        renderBoard();
        return toast(`${crewHeroName(id)} is fallen — that's why they're not here`, "warn");
      }
      if (i >= 0) {
        state.crewBand.splice(i, 1);
        toast(`${crewHeroName(id)} stays at base`, "ok");
      } else {
        state.crewBand.push(id);
        toast(`${crewHeroName(id)} joins the sortie`, "ok");
      }
      if (state.plan) state.plan.deployAces = sealedDeployAces();
      renderCompany();
      renderBoard();
      noteRosterChanged();
      return;
    }

    // Preamble formation: pick exactly seatCap packs.
    if (i >= 0) {
      state.crewBand.splice(i, 1);
      renderCompany();
      renderCompanyIntro();
      return;
    }
    if (state.crewBand.length >= crewSeatCap()) return toast("Pick exactly " + crewSeatCap() + " packs", "err");
    if (crewSpent() + crewHireCost(id) > crewWallet()) return toast("Not enough formation Tnb for that build-power seat", "err");
    state.crewBand.push(id);
    renderCompany();
    renderCompanyIntro();
  }

  function showCompanyIntro() {
    const el = $("company-intro");
    if (!el) return;
    el.classList.add("show");
    try {
      renderCompanyIntro();
    } catch (err) {
      console.error("company intro render failed", err);
      toast("Company picker hit a snag — try Refresh, or pick packs in the left sidebar", "err");
    }
  }
  function hideCompanyIntro() {
    const el = $("company-intro");
    if (el) el.classList.remove("show");
  }
  function syncCompanyIntroGate() {
    if (companySealed()) {
      hideCompanyIntro();
      return false;
    }
    showCompanyIntro();
    return true;
  }
  function renderCompanyIntro() {
    const grid = $("company-intro-grid");
    const coreEl = $("company-intro-core");
    const metaEl = $("company-intro-meta");
    const countEl = $("company-intro-count");
    const sealBtn = $("btn-seal-company-intro");
    if (!grid) return;
    if (companySealed()) {
      hideCompanyIntro();
      return;
    }
    const cap = crewSeatCap();
    const coreIds = crewCoreIds();
    const unlocked = crewBandOrder().filter(id => !coreIds.includes(id));
    // One grid: cores sit where the old duplicate Phobos/rez seats were —
    // sorted eco → startXp → cost with the rest of the roster.
    const gridIds = sortHeroGridIds(coreIds.concat(unlocked));
    if (metaEl) {
      const spent = crewSpent();
      const wallet = crewWallet();
      metaEl.innerHTML =
        `<span class="chip">${unlocked.length} unlocked</span>` +
        `<span class="chip">${coreIds.length} core</span>` +
        `<span class="chip">${state.crewBand.length}/${cap} selected</span>` +
        (spent > 0
          ? `<span class="chip">${wallet - spent}/${wallet} Tnb left (builders)</span>`
          : `<span class="chip">Combat seats free</span>`);
    }
    if (coreEl) coreEl.innerHTML = "";
    const full = state.crewBand.length >= cap;
    grid.innerHTML = gridIds.map(id => {
      const isCore = coreIds.includes(id);
      if (isCore) {
        return renderHeroCard({
          id,
          tag: "core",
          classes: ["core", "on"],
          panel: true,
          compact: true,
          hideCost: true,
          disabled: true,
        });
      }
      const on = state.crewBand.includes(id);
      const cost = crewHireCost(id);
      const costKm = crewHireKm(id);
      const broke = !on && (crewSpent() + cost > crewWallet());
      const lockedPick = (!on && full) || broke;
      const canToggle = !(lockedPick && !on);
      return renderHeroCard({
        id,
        classes: [on ? "on" : "", lockedPick ? "locked" : "", canToggle ? "toggleable" : ""].filter(Boolean),
        costTnb: cost,
        costKm,
        pickable: true,
        showFreeCost: true,
        panel: true,
        compact: true,
        dataCrew: canToggle ? id : null,
        disabled: !canToggle,
        type: "button",
      });
    }).join("") || `<div class="panel-card meta">No unlocked packs yet — recruit in the field.</div>`;
    grid.querySelectorAll("[data-crew]").forEach(btn => {
      btn.onclick = () => toggleCrew(btn.dataset.crew);
    });
    if (countEl) {
      countEl.innerHTML = state.crewBand.length === cap
        ? `Ready · <b>${crewCoreIds().concat(state.crewBand).map(crewHeroName).join(" · ")}</b>`
        : `Pick <b>${cap - state.crewBand.length}</b> more pack${cap - state.crewBand.length === 1 ? "" : "s"}`;
    }
    if (sealBtn) {
      sealBtn.disabled = state.crewBand.length !== cap;
      sealBtn.textContent = state.crewBand.length === cap
        ? "Confirm company"
        : `Confirm (${state.crewBand.length}/${cap})`;
    }
  }

  function wildEntries() {
    const raw = companySurface().wild;
    return Array.isArray(raw) ? raw.filter(w => w && typeof w === "object") : [];
  }
  function wildRecruitsForMap(mapId) {
    const mid = String(mapId || "");
    return wildEntries().filter(w => String(w.mapId || "") === mid);
  }

  function markedZonesForPlan(plan) {
    const m = (plan && plan.marks) || {};
    const out = [];
    for (const z of (m.captureZoneIds || [])) if (z) out.push(String(z));
    if (m.deployZoneId) out.push(String(m.deployZoneId));
    if (m.extractZoneId) out.push(String(m.extractZoneId));
    return [...new Set(out)];
  }

  // Mirror tools/company_v1.field_recruits_for_map: marked pads seat first (up to 3),
  // then ambient fills to limit 2. Hub used to tease EVERY wild pad — that lied
  // about which wrecks Drop actually bakes (~50% "missing wreck" haunt).
  function predictedFieldRecruits(mapId, plan) {
    const mid = String(mapId || "");
    const marked = new Set(markedZonesForPlan(plan));
    const rows = wildRecruitsForMap(mid).map(w => {
      const zone = String(w.zoneId || "");
      let belief = 0.15;
      if (zone && marked.has(zone)) belief += 10;
      const mode = String((w.recruit && w.recruit.type) || w.recruitMode || "wreck_rez");
      if (mode === "wreck_rez" || mode === "retrieve_stash" || mode === "capture") belief += 0.2;
      return {
        id: w.id || w.heroId,
        name: w.name,
        mapId: mid,
        zoneId: zone || null,
        recruit: w.recruit || { type: mode },
        beliefScore: belief,
      };
    });
    rows.sort((a, b) => (b.beliefScore - a.beliefScore) || String(a.id).localeCompare(String(b.id)));
    const limit = 2;
    if (marked.size) {
      const must = rows.filter(r => r.zoneId && marked.has(r.zoneId)).slice(0, 3);
      const rest = rows.filter(r => !must.includes(r));
      const floor = Math.max(limit, must.length);
      const out = must.slice();
      for (const r of rest) {
        if (out.length >= floor) break;
        out.push(r);
      }
      return out.length ? out : rows.slice(0, Math.max(1, limit));
    }
    return rows.slice(0, Math.max(1, limit));
  }

  function wildRecruitAtZone(mapId, zoneId) {
    if (!zoneId) return null;
    const plan = state.plan || { mapId, marks: {} };
    const predicted = predictedFieldRecruits(mapId, plan);
    const hit = predicted.find(r => String(r.zoneId || "") === String(zoneId));
    return hit || null;
  }

  function wildRecruitTeaseAtZone(mapId, zoneId) {
    // Soft teaser for unmarked pads: still name the home hero, but mark as ambient.
    if (!zoneId) return null;
    const hits = wildRecruitsForMap(mapId).filter(w => String(w.zoneId || "") === String(zoneId));
    return hits[0] || null;
  }

  function companyStatusRank(entry) {
    // Sort: deployed → base → dead → locked
    const t = entry.tier || "locked";
    return ({ deployed: 0, base: 1, dead: 2, locked: 3 })[t] ?? 9;
  }

  function buildCompanyEntries() {
    const sealed = companySealed();
    const coreIds = crewCoreIds();
    const deployIds = new Set(sealedDeployAces());
    const ownedBand = companyOwnedBand();
    const laterIds = new Set(list(companySurface().joinedLater));
    const aces = (state.hub.aces || []).slice();
    const aceMap = Object.fromEntries(aces.map(a => [a.id, a]));
    const seen = new Set();
    const entries = [];

    function push(id, tier, extra) {
      if (!id || seen.has(id)) return;
      seen.add(id);
      const ace = aceMap[id] || null;
      const pack = crewPack(id);
      const st = String((ace && ace.status) || (extra && extra.status) || "").toLowerCase();
      let resolved = tier;
      if (st === "dead" || st === "lost") resolved = "dead";
      entries.push(Object.assign({
        id,
        tier: resolved,
        ace,
        pack,
        name: (extra && extra.name) || (ace && ace.name) || crewHeroName(id),
        wild: extra && extra.wild ? extra.wild : null,
      }, extra || {}));
    }

    if (!sealed) {
      // Preamble: sidebar mirrors the intro picks only (full unlocked grid
      // lives on the company-intro modal). Unpicked unlocked stay off-board.
      coreIds.forEach(id => push(id, "deployed", { tag: "core", pickable: false }));
      state.crewBand.forEach(id => push(id, "deployed", { tag: "picked", pickable: true, on: true }));
    } else {
      // Sealed: only this-run company. Dropping ↔ At base. Never dump unlocks.
      deployIds.forEach(id => {
        const isCore = coreIds.includes(id);
        const joined = laterIds.has(id);
        push(id, "deployed", {
          tag: isCore ? "core · always" : (joined ? "field join" : null),
          pickable: true,
          on: true,
        });
      });
      ownedBand.forEach(id => {
        if (deployIds.has(id)) return;
        const ace = aceMap[id];
        const st = String((ace && ace.status) || "active").toLowerCase();
        if (st === "dead" || st === "lost") {
          push(id, "dead", { pickable: false });
          return;
        }
        push(id, "base", {
          tag: laterIds.has(id) ? "field join" : "at base",
          pickable: true,
          on: false,
        });
      });
      // Fallen company / roster heroes only (still no locked dump).
      aces.forEach(a => {
        if (!a || !a.id || seen.has(a.id)) return;
        const st = String(a.status || "").toLowerCase();
        if (st === "dead" || st === "lost") push(a.id, "dead", { pickable: false });
      });
    }

    entries.sort((a, b) => {
      const d = companyStatusRank(a) - companyStatusRank(b);
      if (d !== 0) return d;
      const ac = coreIds.includes(a.id) ? 0 : 1;
      const bc = coreIds.includes(b.id) ? 0 : 1;
      if (ac !== bc) return ac - bc;
      return String(a.name || a.id).localeCompare(String(b.name || b.id));
    });
    return entries;
  }
  function livingCoreIds() {
    return crewCoreIds().filter(heroIsDeployable);
  }
  function droppingPackIds() {
    // Packs on this Drop. Before the first hub sync, assume the whole company
    // so a fast click cannot ship core-only by accident.
    const core = new Set(crewCoreIds());
    if (companySealed() && !state.sortieSynced) {
      return companyOwnedBand().filter(id => !core.has(id) && heroIsDeployable(id));
    }
    return state.crewBand.filter(id => !core.has(id) && heroIsDeployable(id));
  }
  function sealedDeployAces() {
    // Local sortie selection wins: living core + packs marked Dropping.
    // Fallen company members stay on the Fallen list — not the drop confirm.
    return livingCoreIds().concat(droppingPackIds());
  }
  function prettyMapShort(mapId) {
    const id = String(mapId || "");
    const shorts = {
      greenest_fields: "Fields",
      the_rock_jungle: "Jungle",
      eye_of_horus: "Horus",
      koom_valley: "Koom",
      tabula: "Tabula",
      ancient_bastion: "Bastion",
      all_that_simmers: "Simmer",
    };
    if (shorts[id]) return shorts[id];
    const full = prettyMap(id);
    if (full && full !== "—" && full.length <= 14) return full;
    return id.replace(/_/g, " ") || "?";
  }

  function deployChoicesAll() {
    return ((state.hub.node || {}).choices || []).filter(ch => String(ch.kind || "") === "deploy");
  }
  function deployChoicesForMap(mapId) {
    const mid = String(mapId || "");
    return deployChoicesAll().filter(ch => String((ch.effect || {}).mapId || "") === mid);
  }
  function availableMaps() {
    const h = state.hub || {};
    const ids = [];
    const push = (id) => {
      const m = String(id || "").trim();
      if (!m || ids.includes(m)) return;
      ids.push(m);
    };
    // Journey maps first — scales as builder emits more theaters.
    for (const ch of deployChoicesAll()) push((ch.effect || {}).mapId);
    push(h.sessionHomeMap);
    push(h.node && h.node.sortieMapId);
    push(h.node && h.node.regionHint);
    push(h.homeCamp && h.homeCamp.mapId);
    // Respect region selectable flags when present (locked maps stay off chips).
    const regionOk = new Map((h.regions || []).map(r => [r.mapId, r.selectable !== false]));
    const filtered = ids.filter(id => regionOk.size === 0 || regionOk.get(id) !== false);
    if (filtered.length) return filtered;
    // Fresh / empty fallback — the opening pair.
    return ["greenest_fields", "the_rock_jungle"];
  }
  function ensureFocusMapAvailable() {
    const maps = availableMaps();
    if (!maps.length) return null;
    if (maps.includes(state.focusMap)) return state.focusMap;
    const preferred =
      (state.hub.node && (state.hub.node.sortieMapId || state.hub.node.regionHint)) ||
      state.hub.sessionHomeMap ||
      maps[0];
    state.focusMap = maps.includes(preferred) ? preferred : maps[0];
    return state.focusMap;
  }
  function renderMapPicker() {
    const el = $("map-picker");
    if (!el) return;
    const focus = ensureFocusMapAvailable();
    const home = state.hub.sessionHomeMap || (state.hub.homeCamp && state.hub.homeCamp.mapId) || "the_rock_jungle";
    const maps = availableMaps();
    el.innerHTML = maps.map(mapId => {
      const n = deployChoicesForMap(mapId).length;
      const active = mapId === focus;
      const isHome = mapId === home;
      const tags = [];
      if (isHome) tags.push(`<span class="tag-home">home</span>`);
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
          renderNode();
          return;
        }
        state.focusMap = mapId;
        state.selectedZoneId = null;
        renderMapPicker();
        renderRegions();
        renderQuantum();
        refreshTheaterForFocus();
        renderNode();
        logLine(`Operational map → ${prettyMap(mapId)}`);
      };
    });
  }
  function renderCompanyRecruitSlot() {
    const wrap = $("company-recruit");
    const cardEl = $("company-recruit-card");
    const kicker = $("company-recruit-kicker");
    if (!wrap || !cardEl) return null;
    const mapId = (state.plan && state.plan.mapId) || state.focusMap;
    const zoneId = state.selectedZoneId
      || ((state.plan && state.plan.marks && (state.plan.marks.captureZoneIds || [])[0]) || null);
    const hit = wildRecruitAtZone(mapId, zoneId);
    if (!hit) {
      wrap.hidden = true;
      cardEl.innerHTML = "";
      return null;
    }
    const h = crewPack(hit.id);
    const how = ((hit.recruit && hit.recruit.type) || "wreck_rez").replace(/_/g, " ");
    const where = hit.zoneId || zoneId || "zone";
    const blurb = (hit.recruit && hit.recruit.blurb) || h.blurb
      || "Their wreck is on this pad — rez them to join. No live poof.";
    if (kicker) {
      kicker.textContent = `Belief collapse · ${how} · wreck`;
    }
    cardEl.innerHTML = renderHeroCard({
      id: hit.id,
      name: hit.name || crewHeroName(hit.id),
      classes: ["tier-locked", "wild"],
      meta: `${prettyMapShort(hit.mapId || mapId)} · ${where}`,
      blurb,
      panel: true,
      disabled: true,
    });
    wrap.hidden = false;
    return hit.id;
  }

  function renderCompany() {
    const listEl = $("aces");
    const walletEl = $("company-wallet");
    const subEl = $("company-sub");
    const previewText = $("company-preview-text");
    const sealBtn = $("btn-seal-company");
    const col = $("col-aces");
    const theater = $("theater");
    if (!listEl) return;

    const sealed = companySealed();
    const cap = crewSeatCap();
    const capEl = $("company-cap");
    if (col) col.classList.toggle("company-preamble", !sealed);
    if (theater) theater.classList.toggle("company-locked", !sealed);
    // Intro modal owns formation; keep it in sync (or closed once sealed).
    // Never silently leave the picker hidden while the company is unsealed —
    // that freezes the Drop loop looking "greyed out / broken".
    if (sealed) hideCompanyIntro();
    else {
      try { renderCompanyIntro(); } catch (err) { console.error(err); }
    }

    const coreN = livingCoreIds().length;
    const coreNames = livingCoreIds().map(crewHeroName).join(", ");
    const ownedPacks = companyOwnedBand().filter(id => !crewCoreIds().includes(id) && heroIsDeployable(id));
    const dropping = droppingPackIds();
    const staying = ownedPacks.filter(id => !dropping.includes(id));
    if (subEl) {
      subEl.innerHTML = sealed
        ? "Click a pack to leave it at base. Core cannot be left behind."
        : `First run only: pick <b>${cap}</b> packs. Core does not count toward that ${cap}.`;
    }
    if (capEl) {
      if (sealed) {
        const stayNote = staying.length
          ? ` Staying home: <b>${staying.map(crewHeroName).join(", ")}</b>.`
          : "";
        capEl.innerHTML =
          `You can bring <b>every living pack</b> (${ownedPacks.length}). ` +
          `No second cap — the ${cap} was only who joined the company. ` +
          `This drop: <b>${dropping.length} pack${dropping.length === 1 ? "" : "s"}</b> + ` +
          `<b>${coreN} core</b> (${esc(coreNames)}).${stayNote}`;
      } else {
        const left = Math.max(0, cap - state.crewBand.length);
        capEl.innerHTML = left
          ? `Bring <b>${cap} packs</b> besides core. Selected <b>${state.crewBand.length}/${cap}</b> — pick ${left} more. Core (${esc(coreNames)}) always drops.`
          : `Bring <b>${cap} packs</b> besides core. Selected <b>${cap}/${cap}</b>. Confirm to seal. Core (${esc(coreNames)}) always drops.`;
      }
    }
    if (walletEl) {
      if (sealed) {
        const later = list(companySurface().joinedLater);
        const bag = `${crewWallet()} Tnb · ${(crewMetalK() * 1000).toLocaleString()} metal`;
        walletEl.textContent = later.length
          ? `Sealed · ${bag} · +${later.length} join${later.length === 1 ? "" : "s"}`
          : `Sealed · ${bag}`;
      } else {
        const spentTnb = crewSpent();
        const wallet = crewWallet();
        walletEl.textContent = spentTnb > 0
          ? `${wallet - spentTnb}/${wallet} Tnb (builders/reactors) · ${state.crewBand.length}/${cap}`
          : `Combat seats free · ${state.crewBand.length}/${cap}`;
      }
    }
    if (sealBtn) {
      sealBtn.hidden = sealed;
      sealBtn.disabled = sealed || state.crewBand.length !== cap;
      sealBtn.textContent = state.crewBand.length === cap
        ? "Confirm company"
        : `Confirm (${state.crewBand.length}/${cap})`;
    }

    const featuredId = renderCompanyRecruitSlot();
    const entries = buildCompanyEntries().filter(e => e.id !== featuredId);
    const tierLabels = {
      deployed: sealed ? `Dropping · ${dropping.length} packs + ${coreN} core · click a pack to leave it at base` : "Selected",
      base: sealed ? "At base · click to bring on sortie" : "Available · pick for formation",
      dead: "Fallen",
      locked: "Locked",
    };
    let html = "";
    let lastTier = null;
    const capN = crewSeatCap();
    entries.forEach(e => {
      if (e.tier !== lastTier) {
        lastTier = e.tier;
        html += `<div class="company-tier">${esc(tierLabels[e.tier] || e.tier)}</div>`;
      }
      const cost = crewHireCost(e.id);
      const costKm = crewHireKm(e.id);
      const on = !!e.on || (e.tier === "deployed" && !sealed && (crewCoreIds().includes(e.id) || state.crewBand.includes(e.id)));
      // seatCap is the first-run formation pick only. After seal, every living pack can drop.
      const full = !sealed && e.pickable && !on && state.crewBand.length >= capN;
      const broke = !sealed && e.pickable && !on && (crewSpent() + cost > crewWallet());
      const lockedPick = full || broke;
      const wild = e.wild;
      const how = wild ? ((wild.recruit && wild.recruit.type) || "wreck_rez").replace(/_/g, " ") : null;
      const where = wild && wild.mapId ? prettyMapShort(wild.mapId) : null;
      const metaBits = [];
      if (where) metaBits.push(where);
      if (how) metaBits.push(how);
      if (e.ace && e.ace.rank) metaBits.push(e.ace.rank);
      if (e.ace && e.ace.wounds) metaBits.push(`wounded ×${e.ace.wounds}`);
      const blurb = (wild && wild.recruit && wild.recruit.blurb)
        || (e.pack && e.pack.blurb)
        || "";
      const canToggle = !!e.pickable && !(lockedPick && !on);
      html += renderHeroCard({
        id: e.id,
        name: e.name,
        ace: e.ace,
        tag: e.tag || null,
        classes: [
          `tier-${e.tier}`,
          e.tier === "deployed" || on ? "on" : "",
          e.tier === "deployed" ? "deployed" : "",
          crewCoreIds().includes(e.id) ? "core" : "",
          e.tier === "locked" ? "wild" : "",
          lockedPick ? "locked" : "",
          e.ace && e.ace.wounds ? "wounded" : "",
          canToggle ? "toggleable" : "",
        ].filter(Boolean),
        meta: metaBits.join(" · ") || null,
        blurb,
        costTnb: cost,
        costKm,
        pickable: !!e.pickable && !sealed,
        showFreeCost: !!e.pickable && !sealed,
        hideCost: sealed && e.tier !== "deployed" && e.tier !== "base" ? true : false,
        panel: true,
        dataCrew: canToggle ? e.id : null,
        disabled: !canToggle,
        type: "button",
      });
    });
    listEl.innerHTML = html || `<div class="panel-card meta">No company yet.</div>`;
    listEl.querySelectorAll("[data-crew]").forEach(btn => {
      btn.onclick = () => toggleCrew(btn.dataset.crew);
    });

    if (previewText) {
      const drop = sealedDeployAces().map(id => crewHeroName(id));
      const bro = (companySurface().broTzar) || {};
      const callNote = bro.ordered ? " · Tzar ordered" : "";
      previewText.textContent = sealed
        ? (`This drop · ${dropping.length} packs + ${coreN} core` + callNote)
        : (state.crewBand.length === cap
          ? (`Ready · ${cap} packs + ${coreN} core`)
          : `Pick ${cap - state.crewBand.length} more packs (${state.crewBand.length}/${cap}).`);
    }

    // Standing + war panels stay here (were part of renderAces)
    const rep = state.hub.reputation || {};
    if ($("rep")) {
      $("rep").innerHTML = Object.entries(rep).map(([k, v]) =>
        `<div class="panel-card"><div class="row"><span class="rep-name">${esc(repLabel(k))}</span><strong>${esc(v)}</strong></div></div>`
      ).join("");
    }
    const home = state.hub.sessionHomeMap || (state.hub.node && state.hub.node.regionHint);
    const companion = state.hub.companion || {};
    if ($("kernel")) {
      $("kernel").innerHTML = `
        <div class="panel-card">
          <div class="meta">Home ground</div>
          <div class="name" style="font-size:.82rem">${esc(prettyMap(home))}</div>
        </div>
        <div class="panel-card">
          <div class="meta">How we fight</div>
          <div class="name" style="font-size:.82rem">${esc(sessionLabel(state.hub.sessionMode))} · ${esc(occupationLabel(state.hub.occupationModel))}</div>
        </div>
        <div class="panel-card">
          <div class="meta">Ketha of Rhekk's Line</div>
          <div class="meta">Morale ${esc(companion.morale ?? "—")} · Stress ${esc(companion.stress ?? "—")}</div>
        </div>
        <div class="panel-card">
          <div class="meta">Null bay</div>
          <div class="meta">${esc((state.hub.bay && state.hub.bay.hint) || "Still welding")}</div>
        </div>`;
    }

    renderBroTzarButton();
    updateDeployGate();
  }

  // Back-compat aliases — older call sites
  function renderMuster() { renderCompany(); }
  function renderAces() { renderCompany(); }

  function renderBroTzarButton() {
    const btn = $("btn-bro-tzar");
    if (!btn) return;
    // Bro's company seat *is* the Tzar — no paid call-in button.
    btn.hidden = true;
    btn.disabled = true;
  }

  async function orderBroTzar() {
    const bro = (companySurface().broTzar) || {};
    if (bro.inCompany) {
      return toast("Bro is the Tzar — he drops with the company. No Tnb.", "ok");
    }
    return toast("Hire Bro into the company — he is the Tzar", "err");
  }

  function updateDeployGate() {
    const btn = $("btn-deploy");
    if (!btn) return;
    const sealed = companySealed();
    const warmPhase = state.warm && state.warm.phase;
    if (warmPhase === "up") {
      btn.disabled = false;
      btn.classList.add("dropping");
      btn.title = "Recoil is open. This returns to the confirm screen.";
      btn.textContent = "Recoil is open";
      return;
    }
    if (state.dropping || warmPhase === "loading") {
      btn.disabled = false;
      btn.classList.add("dropping");
      btn.title = "The level is loading. Open the confirm screen to see who is shipping.";
      btn.textContent = "Recoil is loading…";
      return;
    }
    btn.classList.remove("dropping");
    // Keep the button enabled when unsealed — it opens the company picker.
    btn.disabled = false;
    if (!sealed) {
      btn.title = "Open the company picker — pick 3 packs, then Confirm";
      btn.textContent = "Form company to Drop";
      return;
    }
    const packs = droppingPackIds().length;
    const coreN = livingCoreIds().length;
    const roster = `${packs} pack${packs === 1 ? "" : "s"} + ${coreN} core`;
    const block = dropBlockReason();
    if (block) {
      btn.title = block;
      btn.textContent = block;
      return;
    }
    btn.title = `This drop ships ${roster}. Core always comes. Choose who deploys after pressing Launch.`;
    btn.textContent = state.hostLive ? `Launch · ${roster}` : `Save plan · ${roster}`;
  }

  function dropBlockReason() {
    if (!companySealed()) return "Form the company first";
    const plan = state.plan;
    if (!plan) return "Pick a sortie on the map first";
    const m = plan.marks || {};
    if (!(m.captureZoneIds && m.captureZoneIds.length)) return "Mark a target on the map first";
    if (!m.deployZoneId) return "Mark an infil pad first";
    return "";
  }

  function dropConfirmOpen() {
    const el = $("drop-confirm");
    return !!(el && el.classList.contains("show"));
  }
  function hideDropConfirm() {
    const el = $("drop-confirm");
    if (el) el.classList.remove("show");
    if (state.warm && state.warm.timer) {
      clearTimeout(state.warm.timer);
      state.warm.timer = null;
    }
  }
  function paintWarmStatus(text) {
    const el = $("drop-warm-status");
    if (!el) return;
    const phase = state.warm && state.warm.phase;
    el.textContent = text || (
      phase === "up" ? "Recoil is open with this company."
      : (phase === "sealing" || phase === "loading") ? "Dropping… The company is locked. The level loads with that roster."
      : phase === "failed" ? "The load did not start. Adjust the company and try again."
      : "Pick who ships, then press Confirm drop. Nothing loads until the company is locked."
    );
  }
  function noteRosterChanged() {
    if (!dropConfirmOpen()) return;
    renderDropSquad();
    paintWarmStatus();
  }
  function sessionIsThisDrop(st) {
    const started = state.warm && state.warm.startedAt;
    if (!started) return false;
    const updated = Date.parse((st && st.updatedAt) || "") || 0;
    return updated + 2000 >= started;
  }
  function renderDropSquad() {
    const squadEl = $("drop-squad");
    const kicker = $("drop-squad-kicker");
    const go = $("drop-confirm-go");
    const coreIds = crewCoreIds();
    const entries = buildCompanyEntries().filter(e => e.tier === "deployed" || e.tier === "base");
    const packN = droppingPackIds().length;
    const coreN = livingCoreIds().length;
    if (kicker) {
      kicker.textContent = entries.length
        ? `Who is dropping · ${packN} pack${packN === 1 ? "" : "s"} + ${coreN} core`
        : "Who is dropping · core only";
    }
    if (squadEl) {
      const locked = dropRosterSealed();
      const cards = entries.map(e => {
        const isCore = coreIds.includes(e.id);
        const on = e.tier === "deployed";
        const canToggle = !isCore && !!e.pickable && !locked;
        return renderHeroCard({
          id: e.id,
          ace: e.ace,
          tag: isCore ? "core · always" : (on ? "dropping" : "at base"),
          classes: [isCore ? "core" : "", on ? "on" : "tier-base", canToggle ? "toggleable" : ""].filter(Boolean),
          compact: true,
          hideCost: true,
          dataCrew: canToggle ? e.id : null,
          disabled: !canToggle,
          type: "button",
        });
      });
      const fallenHome = companyOwnedBand()
        .concat(coreIds)
        .filter((id, i, arr) => arr.indexOf(id) === i && !heroIsDeployable(id));
      let html = cards.join("") || `<div class="theater-sub">Nobody living is marked to drop.</div>`;
      if (fallenHome.length) {
        html += `<div class="theater-sub" style="margin-top:.55rem;color:var(--muted)">Fallen stay home · ${fallenHome.map(crewHeroName).map(esc).join(" · ")}</div>`;
      }
      squadEl.innerHTML = html;
      squadEl.querySelectorAll("[data-crew]").forEach(btn => {
        btn.onclick = () => toggleCrew(btn.dataset.crew);
      });
    }
    if (go) {
      const phase = state.warm && state.warm.phase;
      go.disabled = phase === "loading" || phase === "sealing";
      go.textContent = phase === "up" ? "Back to the map"
        : (phase === "sealing" || phase === "loading") ? "Dropping…"
        : phase === "failed" ? "Try the drop again"
        : "Confirm drop";
    }
  }
  function pollWarm() {
    if (state.warm.poll) clearTimeout(state.warm.poll);
    const tick = async () => {
      if (!state.warm || (state.warm.phase !== "loading" && state.warm.phase !== "sealing" && state.warm.phase !== "up")) return;
      try {
        const statusRes = await fetch(api("/api/status"), { cache: "no-store" });
        const status = await statusRes.json().catch(() => ({}));
        const deployPhase = String((status && status.deployPhase) || "");
        if (state.warm.phase === "loading" && deployPhase === "idle" && !(status && status.busy)) {
          state.warm.locked = false;
          state.warm.phase = "failed";
          paintWarmStatus("The load stopped. Adjust the company and try again.");
          blockDrop("The load stopped before Recoil opened. Try the drop again.");
          renderDropSquad();
          updateDeployGate();
          return;
        }
        if (state.warm.phase === "loading" && (deployPhase === "sealing" || deployPhase === "launching")) {
          state.warm.phase = "sealing";
          state.warm.locked = true;
          paintWarmStatus();
          renderDropSquad();
          updateDeployGate();
        }
        if (deployPhase === "failed" && state.warm.phase !== "up") {
          const err = (status && (status.error || (status.lastDeploy && status.lastDeploy.error))) || "The load did not start.";
          state.warm.locked = false;
          state.warm.phase = "failed";
          paintWarmStatus(String(err));
          blockDrop(String(err));
          renderDropSquad();
          updateDeployGate();
          return;
        }
        const res = await fetch(api("/api/session"), { cache: "no-store" });
        const j = await res.json().catch(() => ({}));
        const st = (j && j.status) || {};
        if (sessionIsThisDrop(st)) {
          const phase = String(st.phase || "");
          const loadingPhase = phase === "building" || phase === "preflight" || phase === "starting" || phase === "dropping";
          // in-game is written only after the level is actually in. A spring
          // pid by itself is still the load, including a previous fight.
          if (phase === "in-game" && st.springPid) {
            const first = state.warm.phase !== "up";
            state.warm.phase = "up";
            state.warm.locked = true;
            paintWarmStatus("Recoil is open with this company.");
            renderDropSquad();
            updateDeployGate();
            if (first) toast("Recoil is open.", "ok");
            state.warm.poll = setTimeout(tick, 3000);
            return;
          }
          if (loadingPhase) {
            state.warm.locked = true;
            if (state.warm.phase === "loading") state.warm.phase = "sealing";
            paintWarmStatus("Dropping… The company is locked. The level is loading.");
            renderDropSquad();
            updateDeployGate();
          }
          if (state.warm.phase === "up" && phase && !loadingPhase && phase !== "in-game") {
            state.warm.phase = "idle";
            state.warm.locked = false;
            paintWarmStatus("Recoil has closed. Choose who ships, then press Confirm drop.");
            renderDropSquad();
            updateDeployGate();
            return;
          }
          if (st.error && state.warm.phase !== "up") {
            state.warm.phase = "failed";
            state.warm.locked = false;
            paintWarmStatus(String(st.error));
            blockDrop(String(st.error));
            renderDropSquad();
            updateDeployGate();
            return;
          }
        }
      } catch (_) { /* keep waiting */ }
      state.warm.poll = setTimeout(tick, 2000);
    };
    state.warm.poll = setTimeout(tick, 1200);
  }

  function showDropConfirm() {
    hideCoach(false);
    hideCompanyIntro();
    hideCampSheet();
    if (!companySealed()) {
      showCompanyIntro();
      return toast("Pick 3 packs and Confirm company first", "warn");
    }
    const plan = state.plan;
    if (!plan) {
      return toast("Mark a route on the theater first", "err");
    }
    if (!(plan.marks && plan.marks.captureZoneIds && plan.marks.captureZoneIds.length)) {
      return toast("Mark a target (wound) on the map first", "err");
    }
    if (!plan.marks.deployZoneId) {
      return toast("Mark an authored deployment zone", "err");
    }
    const board = BOARDS[plan.mapId] || {};
    const zones = board.zones || [];
    const zoneName = (id) => {
      if (!id) return "—";
      const z = zones.find(x => x.zoneId === id);
      return (z && z.label) || id;
    };
    const m = plan.marks || {};
    const targets = (m.captureZoneIds || []).map(zoneName).join(", ") || "—";
    const exfilId = m.extractZoneId || m.deployZoneId;
    const crossMap = exfilId && m.deployZoneId && exfilId !== m.deployZoneId;
    const body = $("drop-confirm-body");
    if (body) {
      body.innerHTML =
        `Drop on <b>${esc(prettyMap(plan.mapId))}</b> · <b>${esc(jobLabel(plan.contractKind))}</b><br>` +
        `Landing <b>${esc(zoneName(m.deployZoneId))}</b> → objective <b>${esc(targets)}</b> → extraction <b>${esc(zoneName(exfilId))}</b>` +
        (crossMap
          ? `<br><span style="color:var(--warn)">Exfil is a different pad — you'll cross the map to leave. Mark exfil on your infil if you want a round trip.</span>`
          : `.`);
      body.innerHTML += `<p><b>Bring them home:</b> Choose Home or Stay in field, then confirm extraction in the battle sidebar. The marked sector must show friendly control and be clear of hostiles. Hold the pad for 10 seconds. Interrupted holds restart; the campaign saves before you leave or continue.</p><p>Engine launch starts after you confirm this deployment.</p>`;
      body.setAttribute("data-route", body.innerHTML);
    }
    const el = $("drop-confirm");
    if (el) el.classList.add("show");
    const phase = state.warm && state.warm.phase;
    if (phase === "loading" || phase === "sealing") {
      renderDropSquad();
      paintWarmStatus();
      return;
    }
    if (phase !== "up") {
      state.warm.phase = "idle";
      state.warm.locked = false;
      if (state.warm.timer) {
        clearTimeout(state.warm.timer);
        state.warm.timer = null;
      }
    }
    renderDropSquad();
    paintWarmStatus();
    if (state.warm.phase === "idle" || state.warm.phase === "failed") noteSpringAlreadyOpen();
  }
  async function noteSpringAlreadyOpen() {
    if (!state.hostLive || !state.warm || (state.warm.phase !== "idle" && state.warm.phase !== "failed")) return;
    try {
      const res = await fetch(api("/api/session"), { cache: "no-store" });
      const j = await res.json().catch(() => ({}));
      const st = (j && j.status) || {};
      if (!state.warm || (state.warm.phase !== "idle" && state.warm.phase !== "failed")) return;
      const phase = String(st.phase || "");
      if (st.springPid || phase === "in-game" || phase === "dropping") {
        paintWarmStatus("Recoil is still open from the last fight. Close it, then press Confirm drop. The company locks on that press, and only then does the level load.");
      }
    } catch (_) { /* sheet stays idle */ }
  }
  function onDropConfirmGo() {
    const phase = state.warm && state.warm.phase;
    if (phase === "up") {
      hideDropConfirm();
      return;
    }
    if (phase === "loading" || phase === "sealing" || state.dropping) {
      paintWarmStatus();
      return;
    }
    if (state.warm && state.warm.timer) {
      clearTimeout(state.warm.timer);
      state.warm.timer = null;
    }
    commitDeploy(true);
  }

  async function sealCompany() {
    if (companySealed()) return toast("Company already sealed", "ok");
    if (state.crewBand.length !== crewSeatCap()) {
      return toast("Pick exactly " + crewSeatCap() + " packs", "err");
    }
    if (!state.hostLive) {
      return toast("Open the wire first (kernel on :8770) to seal the company", "err");
    }
    try {
      toast("Sealing company…");
      const res = await fetch(api("/api/seal-company"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ band: state.crewBand.slice() }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok || j.ok === false) {
        return toast((j && j.error) || "Seal failed", "err");
      }
      if (j.hub) {
        state.hub = j.hub;
      } else {
        await pullHubState();
      }
      // Formation picks become the first sortie roster; rest of catalog stays hidden/locked.
      state.sortieSynced = true;
      syncCrewFromHub();
      hideCompanyIntro();
      renderCompany();
      renderNode();
      refreshTheaterForFocus();
      logLine("Company sealed — " + sealedDeployAces().map(crewHeroName).join(", "));
      toast("Company sealed — only your run roster is on the board.", "ok");
      // After first seal, show the how-to coach once.
      showCoach(false);
    } catch (e) {
      toast("Seal failed: " + e.message, "err");
    }
  }

  function api(path) {
    const base = state.hostBase || "";
    return base + path;
  }

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  })[c]);

  /* Ash Console copy table — keep in sync with match_credit_v1 + va_ash_tokens */
  const VERDICT_UI = {
    victory: { banner: "SUCCESS", headline: "Success." },
    partial: { banner: "PARTIAL SUCCESS", headline: "Partial success." },
    defeat: { banner: "DEFEAT", headline: "Defeat." },
    abandon: { banner: "WITHDRAWN", headline: "Withdrawn." },
    incomplete: { banner: "RESULT PENDING", headline: "Result not home — Retry extract or Abandon." },
  };

  function showHomecoming(opts) {
    const el = $("homecoming");
    if (!el) return;
    const verdict = String((opts && opts.verdict) || "incomplete").toLowerCase();
    const ui = VERDICT_UI[verdict] || VERDICT_UI.incomplete;
    const banner = $("hc-banner");
    const headline = $("hc-headline");
    const hint = $("hc-hint");
    const chips = $("hc-chips");
    if (banner) {
      banner.textContent = (opts && opts.banner) || ui.banner;
      banner.className = "hc-banner " + verdict;
    }
    if (headline) headline.textContent = (opts && opts.headline) || ui.headline;
    if (hint) hint.textContent = (opts && (opts.reasonHint || opts.hint)) || "";
    if (chips) {
      chips.innerHTML = "";
      const list = ((opts && opts.chips) || []).filter(c => !/^(collapse |freeTnbMint|H:)/.test(String(c)));
      list.forEach((c) => {
        if (!c) return;
        const span = document.createElement("span");
        const s = String(c);
        span.className = "hc-chip";
        if (/flip|claim|xp|secured|independents \+/i.test(s)) span.classList.add("good");
        else if (/hinge|partial|scar|no free|collapse|contested|scarcity|void/i.test(s)) span.classList.add("warn");
        else if (/defeat|wiped|lost/i.test(s)) span.classList.add("bad");
        span.textContent = s;
        chips.appendChild(span);
      });
    }
    el.classList.add("show");
  }

  function hideHomecoming() {
    const el = $("homecoming");
    if (el) el.classList.remove("show");
  }

  function toast(msg, kind) {
    const el = $("toast");
    el.textContent = msg;
    el.className = "status-toast show" + (kind ? " " + kind : "");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 4200);
  }

  function logLine(text) {
    state.log.unshift(text);
    state.log = state.log.slice(0, 12);
    $("log").innerHTML = state.log.map(t => `<div>${esc(t)}</div>`).join("");
  }

  function commerce() {
    return state.hub.commerce || { shop: [], deployKit: [], tenebrium: 0, metalK: 0, owned: {}, upgrades: {} };
  }

  function metalKOf(c) {
    c = c || commerce();
    if (c.metalK != null) return Number(c.metalK || 0);
    // Legacy scrapCredits / credits → treat as already-migrated km$ if small, else ÷10.
    const legacy = Number(c.scrapCredits != null ? c.scrapCredits : c.credits || 0);
    return legacy > 40 ? Math.floor(legacy / 10) : legacy;
  }

  function arcMax() {
    return (state.hub.arc && state.hub.arc.maxCaptureMarks) || 1;
  }

  function prettyMap(id) {
    if (!id) return "—";
    const r = (state.hub.regions || []).find(x => x.mapId === id);
    if (r && r.displayName) return r.displayName;
    return String(id).replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function sessionLabel(mode) {
    const m = String(mode || "");
    if (m === "map_travel" || m === "reload_travel") return "On the road";
    if (m === "same_map") return "Holding this ground";
    return m ? m.replace(/_/g, " ") : "Holding this ground";
  }

  function occupationLabel(model) {
    const m = String(model || "living_shell");
    if (m.indexOf("living") >= 0) return "Clear, hold, fortify";
    if (m.indexOf("raid") >= 0) return "Raid and leave scars";
    return m.replace(/_/g, " ");
  }

  function kindLabel(kind) {
    const k = String(kind || "choice").toLowerCase();
    if (k === "deploy") return "sortie";
    if (k === "home_build") return "camp";
    if (k === "shop") return "broker";
    if (k === "talk") return "hearth";
    if (k === "rest") return "rest";
    if (k === "bay") return "garage";
    return k;
  }

  async function doHomeBuild() {
    if (state.hostLive) {
      try {
        toast("Raising the jungle camp…");
        const res = await fetch(api("/api/home-build"), { method: "POST" });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.ok === false) {
          return toast((data && data.error) || "Camp build failed", "err");
        }
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
    renderNode();
    renderBoard();
  }

  function repLabel(k) {
    const map = {
      armada: "Armada", cortex: "Cortex", nullmercs: "Null Mercs",
      ashwalkers: "Ashwalkers", sev: "Sev",
    };
    return map[k] || String(k).replace(/_/g, " ");
  }

  function renderNextStep() {
    const live = state.hostLive;
    const home = state.hub.sessionHomeMap || (state.hub.node && state.hub.node.regionHint);
    const m = state.hub.missionNumber || 1;
    const title = $("ns-title");
    const body = $("ns-body");
    if (!title || !body) return;
    if (!live) {
      title.textContent = "Campfire map — campaign disconnected";
      body.innerHTML =
        `You can study the war from here, but you cannot drop into a fight. ` +
        `Run <b>PLAY.bat</b> (leave it open), then choose a green <b>sortie</b> and <b>Drop into battle</b>.`;
      return;
    }
    const sortie = (state.hub.node && (state.hub.node.sortieMapId || state.hub.node.regionHint)) || state.focusMap;
    if (m <= 1) {
      title.textContent = `Pick a mission`;
      body.innerHTML =
        `Select a <b>map chip</b> above the board (start with <b>${esc(prettyMap(sortie))}</b> or home <b>${esc(prettyMap(home))}</b>). ` +
        `Recommended sorties for that ground appear under the map — mark the route, then <b>Drop</b>. ` +
        `Raise camp from the left <b>Camp</b> chip; buy packs at the <b>Broker</b>.`;
      return;
    }
    const pressure = state.hub.graphPressure || "";
    title.textContent = `Mission ${m} — the front still moves`;
    body.innerHTML =
      `Operational map: <b>${esc(prettyMap(state.focusMap || sortie))}</b> · home <b>${esc(prettyMap(home))}</b> · ${esc(sessionLabel(state.hub.sessionMode))}. ` +
      (pressure ? `World pressure: <b>${esc(pressure)}</b>. ` : "") +
      `Switch maps with the chips above the board; sorties below are the recommended drops for that ground. Your return reveals what changed and which opportunities remain.`;
  }

  function renderBadges() {
    const h = state.hub;
    const live = state.hostLive;
    const arc = h.arc || {};
    $("hud-title").textContent =
      `${(arc.title) || "First Scar"} · sortie ${h.missionNumber || 1}`;
    const home = h.sessionHomeMap || "the_rock_jungle";
    const sortie = (h.node && (h.node.sortieMapId || h.node.regionHint)) || state.focusMap || home;
    const bits = [
      `<span class="badge ${live ? "live" : "warn"}">${live ? "Campaign connected" : "Map only"}</span>`,
      `<span class="badge steam" title="Home you are founding">${esc(prettyMap(home))} home</span>`,
      `<span class="badge gold" title="Briefing / Drop theater">${esc(prettyMap(sortie))} sortie</span>`,
      `<span class="badge">${esc(sessionLabel(h.sessionMode))}</span>`,
      `<span class="badge tnb">Tenebrium ${h.tenebrium ?? commerce().tenebrium ?? 0}</span>`,
      `<span class="badge gold" title="Campaign metal available between sorties">${(metalKOf(commerce()) * 1000).toLocaleString()} metal</span>`,
      (Number(commerce().armyBudget || 0) > 0
        ? `<span class="badge" title="Extracted mobile army — ships as escorts on the next Drop">Army bank ${Math.round(Number(commerce().armyBudget || 0))}</span>`
        : ""),
    ];
    $("hud-badges").innerHTML = bits.join("");
    $("foot-left").textContent = live
      ? `Campaign connected · sortie ${h.missionNumber || 1}`
      : `Map only · run PLAY.bat to fight`;
    renderNextStep();
  }

  function renderRegions() {
    const focus = state.focusMap || (state.hub.node && state.hub.node.regionHint);
    const openIds = new Set(availableMaps());
    const list = state.hub.regions || [];
    $("regions").innerHTML = list.map(r => {
      // Journey maps always open; builder selectable:false locks the rest.
      const locked = !openIds.has(r.mapId) && r.selectable === false;
      const cls = [
        "panel-card", "region",
        r.mapId === focus ? "focus" : "",
        locked ? "locked" : "",
      ].filter(Boolean).join(" ");
      const n = deployChoicesForMap(r.mapId).length;
      return `<div class="${cls}" data-map="${esc(r.mapId)}" data-locked="${locked ? "1" : "0"}">
        <div class="name">${esc(r.displayName || r.mapId)}</div>
        <div class="meta">${esc(r.descriptor || r.family)}${n ? ` · ${n} sortie${n === 1 ? "" : "s"}` : ""}</div>
        <div class="row">
          <span class="ctrl">${esc(r.control)}</span>
          <span>${locked ? "locked" : esc(r.threatBand) + " · " + esc(r.dominantEnemy)}</span>
        </div>
      </div>`;
    }).join("");
    $("regions").querySelectorAll(".region").forEach(el => {
      el.onclick = () => {
        if (el.dataset.locked === "1") {
          toast("That theater is not open yet — finish nearer objectives", "err");
          return;
        }
        state.focusMap = el.dataset.map;
        state.selectedZoneId = null;
        renderMapPicker();
        renderRegions();
        renderQuantum();
        refreshTheaterForFocus();
        renderNode();
        logLine(`Focus theater → ${state.focusMap}`);
      };
    });
  }

  function shopShelfOf(item) {
    const raw = String(item.shelf || "").toLowerCase();
    if (raw) return raw;
    const tags = (item.tags || []).map(t => String(t).toLowerCase());
    if (tags.includes("armada")) return "armada";
    if (tags.includes("nullmercs") || tags.includes("null")) return "nullmercs";
    if (tags.includes("cortex")) return "cortex";
    if (item.kind === "hero_contract") return "nullmercs";
    return "cortex";
  }
  function shopShelfLabel(id) {
    return ({
      cortex: "Cortex · arms merchant",
      armada: "Armada · surplus",
      nullmercs: "Null Mercs",
      camp: "Camp",
    })[id] || id;
  }
  function renderShopListing(item) {
    const locked = !item.available;
    const owned = item.owned;
    const purchaseStack = item.kind === "purchase_package";
    const costs = [];
    if (item.tenebriumCost) costs.push(`${item.tenebriumCost} Tnb`);
    const mkCost = Number(item.metalCostK != null ? item.metalCostK : item.creditCost || 0);
    if (mkCost) costs.push(`${(mkCost * 1000).toLocaleString()} metal`);
    if (!costs.length) costs.push("—");
    const d = item.delivery || {};
    const etaLine = d.summary || d.etaText
      ? `<div class="cost" style="color:var(--steam,#7ec8ff)">${esc(d.summary || d.etaText)}</div>`
      : "";
    const ownedLine = owned
      ? (purchaseStack
          ? `<div class="block" style="color:var(--good)">Owned ×${esc(item.ownedQty || 1)} — buy again to stack</div>`
          : `<div class="block" style="color:var(--good)">In bag / installed</div>`)
      : "";
    const showBuy = purchaseStack || !owned;
    const tags = (item.tags || []).filter(t => !String(t).toLowerCase().startsWith("role:"));
    return `<div class="listing ${owned ? "owned" : ""} ${locked ? "locked" : ""}" data-id="${esc(item.id)}">
      <div class="title">
        <strong>${esc(item.label)}</strong>
        <span class="cost">${esc(costs.join(" · "))}</span>
      </div>
      <div class="blurb">${esc(item.blurb)}</div>
      <details><summary>Pack details</summary><div class="cost">${esc(item.kind.replaceAll("_", " "))}${item.unitDef ? " · " + esc(item.unitDef) : ""}${item.count ? " ×" + esc(item.count) : ""}${item.builds ? " · construction equipment" : ""}</div></details>
      ${etaLine}
      ${locked ? `<div class="block">${esc(item.blockedReason || "locked")}</div>` : ""}
      ${ownedLine}
      <div class="tags">${tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>
      ${showBuy ? `<button type="button" class="btn-buy" data-buy="${esc(item.id)}" ${locked ? "disabled" : ""}>${state.hostLive ? (purchaseStack && owned ? "Buy another" : "Buy") : "Preview buy"}</button>` : ""}
    </div>`;
  }
  function renderShop() {
    const c = commerce();
    $("shop-balances").innerHTML = `
      <div class="bal tnb">Tenebrium<strong>${c.tenebrium ?? 0}</strong>∞ storage</div>
      <div class="bal cred">Metal<strong>${(metalKOf(c) * 1000).toLocaleString()} metal</strong>~${metalKOf(c) * 1000} banked</div>`;
    $("shop-note").textContent =
      (state.hostLive
        ? "Each purchase shows its cost and delivery time. Construction equipment can require Tenebrium as well as metal."
        : "Preview only. Run PLAY.bat to make campaign purchases.");

    const kit = c.deployKit || [];
    const inbound = c.inbound || c.pendingDeliveries || [];
    const kitHtml = kit.length
      ? kit.map(k => `<div class="kit-line"><b>${esc(k.label || k.listingId)}</b>
          ${k.count ? " · ×" + esc(k.count) : ""}
          ${k.loan ? " · loan" : ""}
          ${k.factoryDef ? " · fabricator" : ""}</div>`).join("")
      : "";
    const inboundHtml = inbound.length
      ? inbound.map(k => {
          const d = k.delivery || {};
          return `<div class="kit-line"><b>INBOUND</b> ${esc(k.label || k.listingId)}
            ${k.count ? " · ×" + esc(k.count) : ""}
            ${d.etaText ? " · " + esc(d.etaText) : ""}
            ${d.sourceLabel ? " · from " + esc(d.sourceLabel) : ""}
            ${d.summary ? `<div class="meta">${esc(d.summary)}</div>` : ""}</div>`;
        }).join("")
      : "";
    $("deploy-kit").innerHTML = (kitHtml || inboundHtml)
      ? (kitHtml + inboundHtml)
      : `<div class="kit-line">Empty bag — buy a Punch, stream, or fab before you Drop.</div>`;

    const shop = c.shop || [];
    const order = ["nullmercs", "cortex", "armada", "camp"];
    const groups = {};
    shop.forEach(item => {
      const shelf = shopShelfOf(item);
      (groups[shelf] || (groups[shelf] = [])).push(item);
    });
    const shelfIds = order.filter(id => groups[id] && groups[id].length)
      .concat(Object.keys(groups).filter(id => !order.includes(id)));
    $("shop-list").innerHTML = shelfIds.map(shelf => {
      const rows = groups[shelf].map(renderShopListing).join("");
      return `<div class="shop-shelf">${esc(shopShelfLabel(shelf))}</div>${rows}`;
    }).join("") || `<div class="panel-card meta">Broker is empty — re-export the campaign pack.</div>`;

    $("shop-list").querySelectorAll("[data-buy]").forEach(btn => {
      btn.onclick = () => tryBuy(btn.dataset.buy);
    });
  }

  function recomputeShopAvailability() {
    const c = commerce();
    const rep = state.hub.reputation || {};
    const mission = state.hub.missionNumber || 1;
    const arcN = mission <= 5 ? 1 : mission <= 10 ? 2 : 3;
    const owned = c.owned || {};
    const upgrades = c.upgrades || {};
    (c.shop || []).forEach(item => {
      let ok = true, reason = null;
      const kind = item.kind || "";
      if (kind === "printer_upgrade" && upgrades[item.id]) { ok = false; reason = "upgrade already installed"; }
      if ((kind === "unit_printer" || kind === "loan_package") && owned[item.id]) { ok = false; reason = "already owned"; }
      if (item.starterOwned && item.loan && owned[item.id]) { ok = false; reason = "already owned (starter loan)"; }
      if (item.requires && !owned[item.requires]) { ok = false; reason = "requires " + item.requires; }
      if ((item.arcMin || 1) > arcN) { ok = false; reason = "arc " + item.arcMin + "+ only"; }
      const repMin = item.repMin || {};
      for (const f of Object.keys(repMin)) {
        if (Number(rep[f] || 0) < Number(repMin[f])) {
          ok = false; reason = `need ${f} rep ≥ ${repMin[f]}`;
        }
      }
      const tcost = Number(item.tenebriumCost || 0);
      const mcost = Number(item.metalCostK != null ? item.metalCostK : item.creditCost || 0);
      if (Number(c.tenebrium || 0) < tcost) { ok = false; reason = `need ${tcost} Tenebrium`; }
      if (metalKOf(c) < mcost) { ok = false; reason = `need ${(mcost * 1000).toLocaleString()} metal metal`; }
      item.available = ok;
      item.blockedReason = ok ? null : reason;
      item.owned = !!(owned[item.id] || upgrades[item.id]);
    });
    // rebuild deploy kit labels lightly
    const kit = [];
    for (const [lid, rec] of Object.entries(owned)) {
      if (!rec || typeof rec !== "object") continue;
      const listing = (c.shop || []).find(s => s.id === lid) || {};
      kit.push({
        listingId: lid,
        kind: rec.kind || listing.kind,
        unitDef: rec.unitDef || listing.unitDef,
        count: rec.loanCount || rec.count || listing.count,
        loan: !!(rec.loan || listing.loan),
        label: listing.label || lid,
        factoryDef: rec.factoryDef,
        product: rec.product,
      });
    }
    for (const uid of Object.keys(upgrades)) {
      const listing = (c.shop || []).find(s => s.id === uid) || {};
      kit.push({ listingId: uid, kind: "printer_upgrade", label: listing.label || uid });
    }
    c.deployKit = kit;
    state.hub.tenebrium = c.tenebrium;
    if (state.hub.factionBanks) {
      state.hub.factionBanks.nullmercs = c.tenebrium;
      state.hub.factionBanks.ashwalkers = c.tenebrium;
    }
  }

  async function tryBuy(listingId) {
    if (state.buyBusy) return toast("Purchase already in flight…", "err");
    const c = commerce();
    const item = (c.shop || []).find(s => s.id === listingId);
    if (!item) return toast("Unknown listing", "err");
    recomputeShopAvailability();
    if (!item.available) return toast(item.blockedReason || "Locked", "err");
    const tcost = Number(item.tenebriumCost || 0);
    const mcost = Number(item.metalCostK != null ? item.metalCostK : item.creditCost || 0);

    // Live path: mutate campaign_state via host → story engine purchase_listing
    if (state.hostLive) {
      state.buyBusy = true;
      const buyBtns = document.querySelectorAll(`[data-buy="${CSS.escape(listingId)}"]`);
      buyBtns.forEach(b => { b.disabled = true; });
      try {
        toast("Purchasing…");
        const res = await fetch(api("/api/purchase"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ listingId }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.ok === false) {
          return toast((data && (data.error || data.reason)) || `Buy failed (${res.status})`, "err");
        }
        if (data.commerce) state.hub.commerce = data.commerce;
        if (data.tenebrium != null) state.hub.tenebrium = data.tenebrium;
        if (data.aces) state.hub.aces = data.aces;
        recomputeShopAvailability();
        renderShop();
        renderBadges();
        logLine(`Bought ${item.label} (−${tcost} Tnb, −${(mcost * 1000).toLocaleString()} metal) · campaign bag live`);
        toast(`Bought ${item.label}`, "ok");
        await pullHubState();
        return;
      } catch (e) {
        return toast("Purchase error: " + e.message, "err");
      } finally {
        state.buyBusy = false;
        // renderShop() may have rebuilt buttons; only re-enable if still present
        document.querySelectorAll(`[data-buy="${CSS.escape(listingId)}"]`).forEach(b => {
          if (!b.closest(".listing.locked")) b.disabled = false;
        });
      }
    }

    // Offline demo bag (file://) — does not touch campaign_state
    c.tenebrium = Number(c.tenebrium || 0) - tcost;
    c.metalK = metalKOf(c) - mcost;
    delete c.scrapCredits;
    delete c.credits;
    c.owned = c.owned || {};
    c.upgrades = c.upgrades || {};
    if (item.kind === "printer_upgrade") {
      c.upgrades[listingId] = { installedAtMission: state.hub.missionNumber || 1, requires: item.requires };
    } else {
      const prev = c.owned[listingId] || {};
      const qty = (item.kind === "purchase_package")
        ? (Number(prev.qty || 0) + 1)
        : 1;
      c.owned[listingId] = {
        qty,
        loan: !!item.loan,
        unitDef: item.unitDef,
        loanCount: item.loan ? item.count : null,
        count: item.count,
        kind: item.kind,
        source: "hub_demo_buy",
        delivery: item.delivery || null,
      };
      item.ownedQty = qty;
    }
    c.ledger = c.ledger || [];
    c.ledger.push({ op: "hub_demo_purchase", listingId, tcost, metalCostK: mcost, at: new Date().toISOString() });
    const etaNote = (item.delivery && (item.delivery.summary || item.delivery.etaText))
      ? ` · ${item.delivery.summary || item.delivery.etaText}`
      : "";
    recomputeShopAvailability();
    renderShop();
    renderBadges();
    renderAces();
    logLine(`Acquired ${item.label} (−${tcost} Tnb, −${(mcost * 1000).toLocaleString()} metal)${etaNote}. Demo bag only until campaign settle.`);
    toast(`Acquired ${item.label}${etaNote ? " — " + (item.delivery.etaText || "inbound") : ""} (demo)`, "ok");
    downloadJson(`hub_purchase_${listingId}.json`, {
      schemaVersion: "verdance-hub-purchase-demo/1.0",
      listingId,
      label: item.label,
      tenebriumCost: tcost,
      metalCostK: mcost,
      bag: { tenebrium: c.tenebrium, metalK: c.metalK, owned: c.owned, upgrades: c.upgrades },
      note: "Hub demo mutation. Live: HUB_HOST.bat → POST /api/purchase.",
    });
  }

  function renderCampChip() {
    const chip = $("camp-chip");
    if (!chip) return;
    const camp = state.hub.homeCamp || {};
    const level = Number(camp.level || 0);
    const cleared = !!(camp.cleared || (state.hub.flags && state.hub.flags.homeCleared));
    const ready = !!(camp.clearReady || (state.hub.flags && state.hub.flags.homeClearReady));
    if ($("camp-chip-label")) $("camp-chip-label").textContent = `Camp L${level}`;
    if ($("camp-chip-meta")) {
      $("camp-chip-meta").textContent = cleared
        ? "cleared"
        : (ready ? "clear-ready · open" : "raise · open");
    }
  }
  function pinCampSheetToCompanyBar() {
    const el = $("camp-sheet");
    const col = document.body.classList.contains("command-console") ? $("main") : $("col-aces");
    if (!el || !col) return;
    const r = col.getBoundingClientRect();
    el.style.left = `${Math.max(0, r.left)}px`;
    el.style.top = `${Math.max(0, r.top)}px`;
    el.style.width = `${Math.max(160, r.width)}px`;
    el.style.height = `${Math.max(200, r.height)}px`;
  }
  function showCampSheet() {
    const el = $("camp-sheet");
    if (!el) return;
    renderCampSheet();
    pinCampSheetToCompanyBar();
    el.classList.add("show");
  }
  function hideCampSheet() {
    const el = $("camp-sheet");
    if (el) el.classList.remove("show");
  }
  function renderCampSheet() {
    const camp = state.hub.homeCamp || {};
    const c = commerce();
    const level = Number(camp.level || 0);
    const cleared = !!(camp.cleared || (state.hub.flags && state.hub.flags.homeCleared));
    const ready = !!(camp.clearReady || (state.hub.flags && state.hub.flags.homeClearReady));
    const tCost = Number(camp.raiseTnbCost != null ? camp.raiseTnbCost : 1);
    const mCost = Number(camp.raiseMetalCostK != null ? camp.raiseMetalCostK : 1);
    const canRaise = camp.canRaise != null
      ? !!camp.canRaise
      : (!cleared && Number(c.tenebrium || 0) >= tCost && metalKOf(c) >= mCost);
    if ($("camp-sheet-title")) {
      $("camp-sheet-title").textContent = camp.label || "Jungle camp";
    }
    if ($("camp-sheet-lede")) {
      $("camp-sheet-lede").textContent = cleared
        ? "Shelf is clear — keep funding sorties from the broker."
        : "Raise the shelf here. The main screen is for picking missions.";
    }
    if ($("camp-sheet-stats")) {
      $("camp-sheet-stats").innerHTML =
        `<span class="chip">L${level}</span>` +
        `<span class="chip">${esc(prettyMap(camp.mapId || state.hub.sessionHomeMap || "the_rock_jungle"))}</span>` +
        `<span class="chip">${Number(c.tenebrium || 0)} Tnb</span>` +
        `<span class="chip">${(metalKOf(c) * 1000).toLocaleString()} metal</span>` +
        (cleared ? `<span class="chip">cleared</span>` : "") +
        (ready && !cleared ? `<span class="chip">clear-ready</span>` : "") +
        (camp.commanderLine != null
          ? `<span class="chip">${camp.commanderUnlocked ? "command walker" : "walker scrap"}</span>`
          : "");
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

  let hearthPending = null;

  function aceName(id) {
    const ace = ((state.hub && state.hub.aces) || []).find(a => a && a.id === id);
    if (ace && ace.name) return ace.name;
    const pack = (window.VA_CREW_PACKS && window.VA_CREW_PACKS.heroes && window.VA_CREW_PACKS.heroes[id]) || null;
    if (pack && pack.name) return pack.name;
    return id;
  }

  function hearthEligible() {
    const sw = (state.hub && state.hub.supportWeb) || {};
    let list = Array.isArray(sw.eligibleTalks) ? sw.eligibleTalks.slice() : [];
    if (!list.length && window.VA_CAMP_TALKS && Array.isArray(window.VA_CAMP_TALKS.talks)) {
      // Offline fallback: authored C talks for sealed company circle
      const circle = new Set(sw.circle || []);
      if (!circle.size) {
        const co = state.hub.company || {};
        ["core", "band", "joinedLater"].forEach(k => {
          (co[k] || []).forEach(x => {
            const id = (x && typeof x === "object") ? (x.id || x.heroId) : x;
            if (id) circle.add(String(id));
          });
        });
      }
      list = window.VA_CAMP_TALKS.talks.filter(t =>
        t && t.rank === "C" && circle.has(String(t.a)) && circle.has(String(t.b))
      ).slice(0, 8);
    }
    return list;
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
    listEl.innerHTML = talks.map(t => {
      const authored = t.authored ? " · hand" : "";
      return `<button type="button" class="hearth-talk" data-talk-id="${esc(t.id)}">
        <div class="ht-title">${esc(t.title || t.id)} <span style="opacity:.7">[${esc(t.rank || "C")}]</span></div>
        <div class="ht-meta"><b>${esc(aceName(t.a))}</b> · <b>${esc(aceName(t.b))}</b> · ${esc(t.polarity || "")}${authored}</div>
      </button>`;
    }).join("");
    listEl.querySelectorAll(".hearth-talk").forEach(btn => {
      btn.onclick = () => previewHearthTalk(btn.getAttribute("data-talk-id"));
    });
  }

  function findTalkById(tid) {
    const sw = (state.hub && state.hub.supportWeb) || {};
    const fromHub = (sw.eligibleTalks || []).find(t => t && t.id === tid);
    if (fromHub) return fromHub;
    const all = (window.VA_CAMP_TALKS && window.VA_CAMP_TALKS.talks) || [];
    return all.find(t => t && t.id === tid) || null;
  }

  function previewHearthTalk(tid) {
    const talk = findTalkById(tid);
    if (!talk) return toast("Talk missing", "err");
    hearthPending = talk;
    const stage = $("hearth-stage");
    const title = $("hearth-stage-title");
    const beatsEl = $("hearth-stage-beats");
    if (!stage || !beatsEl) return;
    if (title) {
      title.textContent = `${talk.title || tid} · ${aceName(talk.a)} & ${aceName(talk.b)}`;
    }
    const beats = talk.beats || [];
    beatsEl.innerHTML = beats.map(b => {
      const who = b.speaker === "narrator" ? "Hearth" : aceName(b.speaker);
      const cls = b.speaker === "narrator" ? "hs-beat narrator" : "hs-beat";
      return `<div class="${cls}"><span class="who">${esc(who)}</span>${esc(b.line || "")}</div>`;
    }).join("");
    stage.classList.add("show");
  }

  async function confirmHearthTalk() {
    if (!hearthPending) return;
    const talk = hearthPending;
    if (state.hostLive) {
      try {
        const res = await fetch(api("/api/camp-talk"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ talkId: talk.id, a: talk.a, b: talk.b }),
        });
        const data = await res.json();
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
    // Demo / offline: bump local ace bonds + mark talk done on supportWeb
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
    if (row.points >= 55) row.rank = "A";
    else if (row.points >= 25) row.rank = "B";
    else row.rank = "C";
    pb[pid] = row;
    // Drop this talk from eligible
    state.hub.supportWeb.eligibleTalks = (state.hub.supportWeb.eligibleTalks || [])
      .filter(t => t && t.id !== talk.id);
    toast(`Hearth holds (demo) — ${talk.title}`, "ok");
    logLine(`Demo support talk ${talk.id}`);
    renderHearthList();
    renderCompany();
  }

  function cancelHearthTalk() {
    hearthPending = null;
    const stage = $("hearth-stage");
    if (stage) stage.classList.remove("show");
  }

  async function raiseCampFromSheet() {
    hideCampSheet();
    await doHomeBuild();
    renderCampChip();
    renderCampSheet();
  }
  function openFoundingSortieFromCamp() {
    hideCampSheet();
    const choices = ((state.hub.node || {}).choices || []);
    const founding = choices.find(ch =>
      ch && ch.kind === "deploy" && (
        (ch.effect && ch.effect.journey === "home_founding") ||
        String((ch.effect && ch.effect.mapId) || "") === "the_rock_jungle" ||
        /rock jungle|found/i.test(String(ch.label || ""))
      )
    );
    state.focusMap = "the_rock_jungle";
    renderMapPicker();
    renderNode();
    if (founding) {
      onChoice(founding.id);
      return;
    }
    refreshTheaterForFocus();
    toast("Mark the Rock Jungle founding route, then Drop", "ok");
  }
  function openBrokerFromCamp() {
    hideCampSheet();
    const tab = $("tab-shop");
    if (tab) tab.click();
    else {
      ["shop", "theaters", "manifold"].forEach(name => {
        const panel = $("panel-" + name);
        if (panel) panel.hidden = name !== "shop";
      });
      document.querySelectorAll(".tab").forEach(t => {
        t.classList.toggle("active", t.dataset.tab === "shop");
      });
    }
    toast("Broker open — buy before you Drop", "ok");
  }

  function renderNode() {
    const h = state.hub;
    const node = h.node || {};
    const home = h.sessionHomeMap || node.regionHint;
    const arcTitle = (h.arc && h.arc.title) || "First Scar";
    $("kicker").textContent =
      `${arcTitle} · sortie ${h.missionNumber || 1} · ${prettyMap(home)}`;
    $("title").textContent = h.tagline || "The green is dying. Ashwalkers hold the line.";
    const nullRep = Number((h.reputation || {}).nullmercs || 0);
    $("sub").textContent =
      `${sessionLabel(h.sessionMode)} · ${occupationLabel(h.occupationModel)}` +
      (nullRep ? ` · Null Mercs know you (${nullRep})` : "");
    const speaker = (node.speaker || "ketha");
    const speakerName = speaker === "ketha" ? "Ketha of Rhekk's Line" :
      (speaker.charAt(0).toUpperCase() + speaker.slice(1));
    if ($("voice-who")) $("voice-who").textContent = speakerName;
    $("voice").textContent = node.text || "The line is quiet. That never lasts.";
    // Main screen = recommended sorties for the selected operational map only.
    const focus = ensureFocusMapAvailable() || state.focusMap;
    const choices = deployChoicesForMap(focus);
    const mapLabel = $("choices-map-label");
    if (mapLabel) mapLabel.textContent = prettyMap(focus);
    const head = $("choices-head");
    if (head) {
      const kicker = head.querySelector(".ch-kicker");
      if (kicker) {
        kicker.textContent = choices.length
          ? "Recommended sorties"
          : "No sorties on this map";
      }
    }
    $("choices").innerHTML = choices.map(ch => {
      const kl = kindLabel(ch.kind);
      const isSortie = ch.kind === "deploy";
      const leanCls = ch.recommended ? " lean" : (isSortie ? " residual" : "");
      const cls = (isSortie ? "deploy battle" : (ch.kind || "")) + leanCls;
      const blurb = ch.blurb
        || (isSortie ? "Mark the ground. Drop. Come home." : "");
      const disabled = !!ch.disabled;
      return `<button type="button" class="choice ${esc(cls)}" data-choice="${esc(ch.id)}" ${disabled ? "disabled" : ""}>
        <div class="kind ${esc(kl)}">${esc(kl)}${disabled ? " · locked" : ""}</div>
        <div class="label">${esc(ch.label)}</div>
        ${blurb ? `<div class="blurb">${esc(blurb)}</div>` : ""}
      </button>`;
    }).join("") || `<div class="panel-card meta">No recommended sorties on <b>${esc(prettyMap(focus))}</b> — pick another map above, or refresh after the last fight.</div>`;
    $("choices").querySelectorAll(".choice").forEach(btn => {
      btn.onclick = () => {
        if (btn.disabled) return toast("That journey is locked — raid for Tnb first", "err");
        onChoice(btn.dataset.choice);
      };
    });
    renderMapPicker();
    renderCampChip();
    renderNextStep();
  }

  function onChoice(id) {
    const ch = ((state.hub.node || {}).choices || []).find(c => c.id === id);
    if (!ch) return;
    const kind = ch.kind || "";
    if (kind === "deploy") {
      openDeploy(ch);
      return;
    }
    if (kind === "home_build") {
      doHomeBuild();
      return;
    }
    if (kind === "shop") {
      document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === "shop"));
      $("panel-shop").hidden = false;
      $("panel-theaters").hidden = true;
      if ($("panel-manifold")) $("panel-manifold").hidden = true;
      logLine("The broker's tent is open.");
      toast("Broker — hire before you drop", "ok");
      return;
    }
    if (kind === "talk") {
      const delta = (ch.effect && ch.effect.bondDelta) || {};
      for (const ace of state.hub.aces || []) {
        const d = delta[ace.id];
        if (d) {
          ace.bonds = ace.bonds || {};
          for (const [k, v] of Object.entries(d)) ace.bonds[k] = (ace.bonds[k] || 0) + Number(v);
        }
      }
      logLine("Ketha stays by the fire a little longer. Bonds warm.");
      toast("The hearth holds", "ok");
      renderAces();
      return;
    }
    if (kind === "rest") {
      for (const ace of state.hub.aces || []) {
        if (ace.wounds > 0) ace.wounds = Math.max(0, ace.wounds - 1);
      }
      if (state.hub.companion && state.hub.companion.stress != null) {
        state.hub.companion.stress = Math.max(0, Number(state.hub.companion.stress) - 5);
      }
      logLine("The company sleeps. Wounds ease. Stress bleeds off.");
      toast("The company rests", "ok");
      renderAces();
      return;
    }
    if (kind === "bay") {
      toast((ch.effect && ch.effect.note) || "Bay still locked", "err");
      logLine("Null bay is still welding. Come back when the contract deepens.");
      return;
    }
    logLine(`Choice ${id} (${kind})`);
  }

  const RIM_THRESHOLD = 0.28;
  const ENEMY_CTRL = new Set(["armada", "cortex", "wild"]);

  function edgeScore(z) {
    if (z && z.edgeScore != null) return Number(z.edgeScore);
    const b = (z && z.bounds) || {};
    const cx = ((Number(b.xMin) || 0) + (Number(b.xMax) || 1)) / 2;
    const cz = ((Number(b.zMin) || 0) + (Number(b.zMax) || 1)) / 2;
    return Math.min(cx, 1 - cx, cz, 1 - cz);
  }

  function isRimZone(z) {
    return edgeScore(z) <= RIM_THRESHOLD;
  }

  function claimRecordFor(mapId, zoneId) {
    const mid = String(mapId || "");
    const zid = String(zoneId || "");
    if (!mid || !zid) return null;
    // Raw ledger: nodeClaims / claimedNodes as { mapId: { zoneId: rec } }
    const ledgers = [state.hub.nodeClaims, state.hub.claimedNodes];
    for (const led of ledgers) {
      if (!led || typeof led !== "object") continue;
      const byMap = led[mid];
      if (byMap && typeof byMap === "object" && !Array.isArray(byMap)) {
        const rec = byMap[zid];
        if (rec) return rec;
      }
      // Hub claim surface: { nodes: [{mapId, zoneId, ...}] }
      if (Array.isArray(led.nodes)) {
        const hit = led.nodes.find(n => n && n.mapId === mid && n.zoneId === zid);
        if (hit) return hit;
      }
    }
    return null;
  }
  function openContractFor(mapId, zoneId) {
    const mid = String(mapId || "");
    const zid = String(zoneId || "");
    const contracts = state.hub.captureContracts || [];
    return contracts.find(c => c && c.mapId === mid && (c.targetZoneId || c.zoneId) === zid) || null;
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
    const out = base || {
      zoneId,
      label: (open && open.label) || zoneId,
      control: "unknown",
      confidence: open ? "contract" : "estimated",
      openTarget: false,
      claimed: false,
      preferred: false,
      hazard: 0,
    };
    if (claim) {
      out.claimed = true;
      if (!out.control || out.control === "unknown") {
        out.control = claim.newControl || claim.patron || "ashwalkers";
      }
    }
    if (open) {
      out.openTarget = true;
      out.preferred = true;
      if (open.label) out.label = open.label;
    }
    return out;
  }
  function zoneInOps(mapId, z) {
    if (!z) return false;
    const intel = intelFor(mapId, z.zoneId) || {};
    if (intel.claimed || intel.openTarget || intel.preferred) return true;
    const ctrl = String(intel.control || "").toLowerCase();
    if (ctrl === "ashwalkers" || ctrl === "legion") return true;
    if (isLegalLanding(mapId, z)) return true;
    // Preferred capture / infil from the active plan always stay in footprint.
    const m = (state.plan && state.plan.marks) || {};
    if (m.deployZoneId === z.zoneId || m.extractZoneId === z.zoneId) return true;
    if ((m.captureZoneIds || []).includes(z.zoneId)) return true;
    return false;
  }

  function zoneControl(mapId, zoneId, z) {
    const intel = intelFor(mapId, zoneId) || {};
    return String(intel.control || (z && z.control) || "unknown").toLowerCase();
  }

  function isContestedApproach(mapId, z) {
    if (!z) return true;
    const ctrl = zoneControl(mapId, z.zoneId, z);
    if (ENEMY_CTRL.has(ctrl)) return true;
    const tags = (z.tags || []).map(t => String(t).toLowerCase());
    const role = String(z.role || "").toLowerCase();
    if (tags.includes("contested") || role.includes("contested")) return true;
    if ((tags.includes("fortress") || tags.includes("bastion") || /fortress|bastion|citadel/.test(role))
        && ctrl !== "ashwalkers" && ctrl !== "nullmercs") {
      return true;
    }
    return false;
  }

  function isAshwalkerBase(mapId, zoneId) {
    const intel = intelFor(mapId, zoneId) || {};
    const ctrl = String(intel.control || "").toLowerCase();
    // Claimed scars / FOBs count even if control string is briefly stale.
    if (intel.claimed) return true;
    return ctrl === "ashwalkers" || ctrl === "legion";
  }

  function isLegalLanding(mapId, z) {
    if (!z) return false;
    // Hard rim-only lock is gone: inland pads are fine when we hold them.
    if (isAshwalkerBase(mapId, z.zoneId)) return true;
    return isRimZone(z) && !isContestedApproach(mapId, z);
  }

  function zoneCenter(z) {
    const b = (z && z.bounds) || {};
    return {
      x: (((Number(b.xMin) || 0) + (Number(b.xMax) || 1)) / 2) * 100,
      y: (((Number(b.zMin) || 0) + (Number(b.zMax) || 1)) / 2) * 100,
    };
  }

  function zonePoint(z) {
    const a = z && z.anchor;
    if (a && a.x != null && a.z != null) return { x: Number(a.x), z: Number(a.z) };
    const b = (z && z.bounds) || {};
    return {
      x: ((Number(b.xMin) || 0) + (Number(b.xMax) || 1)) / 2,
      z: ((Number(b.zMin) || 0) + (Number(b.zMax) || 1)) / 2,
    };
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
    let best = null;
    let bestD = 1e9;
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

  // Far dry corners stay on the board as pads the player can mark, but a
  // sortie's default exfil is the near shore. Rock Jungle's river is not a walk.
  function snapGroundRoute(mapId, marks) {
    const targetId = (marks.captureZoneIds || [])[0];
    if (!targetId) return;
    const near = nearestDryPad(mapId, targetId);
    if (!near) return;
    if (!padIsNear(mapId, marks.deployZoneId, targetId)) marks.deployZoneId = near.zoneId;
    if (!padIsNear(mapId, marks.extractZoneId, targetId)) {
      marks.extractZoneId = padIsNear(mapId, marks.deployZoneId, targetId)
        ? marks.deployZoneId
        : near.zoneId;
    }
  }

  function defaultMarks(mapId) {
    const board = BOARDS[mapId] || {};
    const zones = board.zones || [];
    // Infil / exfil: quiet rim or Ashwalker bases; prefer inter-map lanes.
    const legal = zones.filter(z => isLegalLanding(mapId, z));
    const byEdge = legal.slice().sort((a, b) => {
      const owned = (z) => (isAshwalkerBase(mapId, z.zoneId) ? 0 : 1);
      const lane = (z) => (z && z.interMapLane) ? 0 : 1;
      return (owned(a) - owned(b)) || (lane(a) - lane(b)) || (edgeScore(a) - edgeScore(b));
    });
    const rim = byEdge.filter(z => isRimZone(z));
    const lanes = rim.filter(z => z.interMapLane);
    const owned = byEdge.filter(z => isAshwalkerBase(mapId, z.zoneId));
    const deployPool = owned.length
      ? owned
      : (lanes.length ? lanes : (rim.length ? rim : byEdge));
    const deploy =
      deployPool.find(z => z.deployDefault) ||
      deployPool.find(z => z.interMapLane) ||
      deployPool.find(z => /start|staging|shelf|camp|muster/i.test(String(z.role || "") + " " + (z.tags || []).join(" "))) ||
      deployPool[0] ||
      zones[0];
    // Default exfil = same pad as infil (round-trip raid). Opposite-side
    // interMapLane used to auto-pick SE when you landed NW — that forced a
    // full-map crossing just to leave. Player can still mark a far exfil.
    const extract =
      deployPool.find(z => z.extractDefault && z === deploy) ||
      deploy ||
      deployPool.find(z => z.extractDefault) ||
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
      extractZoneId: extract && extract.zoneId,
      captureZoneIds: pick ? [pick.zoneId] : [],
    };
  }

  function jobLabel(kind) {
    return ({
      eco_raid: "Raid their economy",
      seize_lane: "Seize and hold the lane",
      strike_relay: "Cut the relay",
      destroy_key_structure: "Break the key structure",
      hive_clear_or_bypass: "Clear or bypass the hive",
      gate_control: "Hold the gate",
      home_clear: "Clear the home wilds",
      fortify_zone: "Fortify and secure the zone",
      secure_foothold: "Secure the foothold",
      home_founding: "Found the camp — dig in",
    })[kind] || String(kind || "Sortie").replace(/_/g, " ");
  }

    function ensureTheaterPlan(choice) {
      const effect = (choice && choice.effect) || {};
    const mapId = effect.mapId
      || state.focusMap
      || state.hub.sessionHomeMap
      || (state.hub.node && state.hub.node.regionHint)
      || "the_rock_jungle";
    const marks = defaultMarks(mapId);
      if (effect.preferredCaptureZoneId) {
        marks.captureZoneIds = [effect.preferredCaptureZoneId];
      }
      if (effect.captureZoneIds && effect.captureZoneIds.length) {
        marks.captureZoneIds = effect.captureZoneIds.slice();
      }
      const preferredDeploy = effect.preferredDeployZoneId || effect.deploymentZoneId;
      if (preferredDeploy) {
        const board = BOARDS[mapId] || {};
        const z = (board.zones || []).find(x => x.zoneId === preferredDeploy);
        // Honor story/engine pads even when midfield — LZ legality is stamp-side.
        if (z || preferredDeploy) {
          marks.deployZoneId = preferredDeploy;
          if (!marks.extractZoneId) marks.extractZoneId = preferredDeploy;
        }
      }
      const preferredExtract = effect.preferredExtractionZoneId || effect.extractionZoneId;
      if (preferredExtract) {
        marks.extractZoneId = preferredExtract;
      }
      const mouthIn = effect.infilZoneId;
      const mouthOut = effect.exfilZoneId;
      const mouthCard = !!(effect.wetReach && mouthIn && mouthOut);
      if (mouthCard) {
        marks.deployZoneId = mouthIn;
        marks.extractZoneId = mouthOut;
      }
    const against = effect.against
      || (mapId === "eye_of_horus" ? "cortex" : mapId === "the_rock_jungle" ? "wild" : "armada");
    state.plan = {
      schemaVersion: "verdance-deploy-plan/1.0",
      mapId,
      contractKind: effect.contractKind || (mapId === "the_rock_jungle" ? "hive_clear_or_bypass" : "seize_lane"),
      // Drop roster = packs currently in Dropping (from THE COMPANY sidebar).
      deployAces: sealedDeployAces(),
      crewBand: state.crewBand.slice(),
      choiceId: (choice && choice.id) || "c_theater",
      repDelta: effect.repDelta || {},
      arcId: (state.hub.arc && state.hub.arc.id) || 1,
      maxCaptureMarks: arcMax(),
      marks,
      pathSignal: state.hub.pathSignal,
      sessionMode: effect.sessionMode || state.hub.sessionMode || "same_map",
      occupationModel: state.hub.occupationModel || "living_shell",
      commerceDeploy: {
        tenebrium: commerce().tenebrium,
        kit: commerce().deployKit || [],
      },
      patron: "nullmercs",
      against,
      wetReach: !!(effect.wetReach && effect.infilZoneId && effect.exfilZoneId),
      infilZoneId: effect.infilZoneId || null,
      exfilZoneId: effect.exfilZoneId || null,
      headingMapId: effect.headingMapId || null,
      headingZoneId: effect.headingZoneId || null,
      alongTheWay: (effect.alongTheWay || []).slice(),
    };
    if (!state.plan.wetReach) snapGroundRoute(mapId, marks);
    state.markMode = state.markMode || "capture";
    state.focusMap = mapId;
    return state.plan;
  }

  function openDeploy(choice) {
    ensureTheaterPlan(choice);
    state.markMode = "capture";
    document.querySelectorAll(".mode-btn").forEach(b => b.classList.toggle("active", b.dataset.mode === state.markMode));
    updateDeployGate();
    renderBoard();
    const plan = state.plan;
    logLine(`Route briefing — ${prettyMap(plan.mapId)} · ${jobLabel(plan.contractKind)}`);
    toast(`Mark the target on ${prettyMap(plan.mapId)}`, "ok");
    const th = $("theater");
    if (th) th.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function refreshTheaterForFocus() {
    const mapId = ensureFocusMapAvailable()
      || state.focusMap
      || state.hub.sessionHomeMap
      || (state.hub.node && state.hub.node.regionHint)
      || "the_rock_jungle";
    const prevMap = state.plan && state.plan.mapId;
    // Prefer a deploy choice matching this map if present
    const choices = deployChoicesForMap(mapId);
    const match = choices[0] || null;
    if (match) ensureTheaterPlan(match);
    else ensureTheaterPlan({ id: "c_theater", effect: { mapId } });
    // Drop zone selection when the theater map changes.
    if (prevMap && prevMap !== mapId) state.selectedZoneId = null;
    renderBoard();
    renderCompany();
  }

  function drawRouteArrows(plan, zones) {
    const svg = $("board-route");
    if (!svg) return;
    const m = (plan && plan.marks) || {};
    const byId = Object.fromEntries((zones || []).map(z => [z.zoneId, z]));
    const infil = byId[m.deployZoneId];
    const targetId = (m.captureZoneIds || [])[0];
    const target = byId[targetId];
    const exfil = byId[m.extractZoneId];
    const parts = [];
    parts.push(`<defs>
      <marker id="arr-warn" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
        <path d="M0,0 L5,2.5 L0,5 Z" fill="#e0a060"/></marker>
      <marker id="arr-steam" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
        <path d="M0,0 L5,2.5 L0,5 Z" fill="#7ec8ff"/></marker>
    </defs>`);
    if (infil && target) {
      const a = zoneCenter(infil), b = zoneCenter(target);
      parts.push(`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
        stroke="#e0a060" stroke-width="0.9" stroke-opacity="0.9"
        marker-end="url(#arr-warn)"/>`);
    }
    if (target && exfil) {
      const a = zoneCenter(target), b = zoneCenter(exfil);
      parts.push(`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
        stroke="#7ec8ff" stroke-width="0.85" stroke-opacity="0.85" stroke-dasharray="2 1.5"
        marker-end="url(#arr-steam)"/>`);
    }
    svg.innerHTML = parts.join("");
  }

  function renderBoard() {
    if (!state.plan) refreshTheaterForFocus();
    const plan = state.plan;
    if (!plan) return;
    const board = BOARDS[plan.mapId] || { zones: [] };
    const zones = board.zones || [];
    const el = $("board-zones") || $("board");
    const title = $("theater-title");
    const sub = $("theater-sub");
    if (title) title.textContent = prettyMap(plan.mapId);
    if (sub) {
      const camp = (state.hub.homeCamp && state.hub.homeCamp.level) || 0;
      const flags = state.hub.flags || {};
      const homeNote = plan.mapId === "the_rock_jungle"
        ? (flags.homeCleared
          ? " · home cleared"
          : ` · camp L${camp}${flags.homeClearReady ? " · clear ready" : " · need Tnb to scale"}`)
        : "";
      sub.textContent =
        `${jobLabel(plan.contractKind)} · ${(plan.deployAces || []).join(", ") || "your aces"}${homeNote}`;
    }
    const lzMode = state.markMode === "deploy" || state.markMode === "extract";
    if (!zones.length) {
      el.innerHTML = `<div style="padding:1rem;color:var(--muted);font-size:.85rem">
        No zone board for <b>${esc(plan.mapId)}</b>. Run tools/build_zone_boards_v1.py.</div>`;
      drawRouteArrows(plan, []);
    } else {
      el.innerHTML = zones.map(z => {
        const b = z.bounds || { xMin:0, xMax:0.2, zMin:0, zMax:0.2 };
        const left = (b.xMin || 0) * 100;
        const top = (b.zMin || 0) * 100;
        const w = Math.max(4, ((b.xMax || 0) - (b.xMin || 0)) * 100);
        const h = Math.max(4, ((b.zMax || 0) - (b.zMin || 0)) * 100);
        const m = plan.marks || {};
        const intel = intelFor(plan.mapId, z.zoneId) || {};
        const cls = ["zone"];
        if (z.capturable) cls.push("capturable");
        if (isRimZone(z)) cls.push("rim-eligible");
        else cls.push("midfield");
        if (isLegalLanding(plan.mapId, z)) cls.push("lz-eligible");
        if (lzMode) cls.push("mode-lz");
        if (intel.openTarget || intel.preferred) cls.push("open-target");
        if (intel.claimed) cls.push("claimed");
        if (intel.control) cls.push("ctrl-" + String(intel.control).replace(/[^a-z]/g, ""));
        if (intel.confidence === "estimated") cls.push("est");
        if (m.deployZoneId === z.zoneId) cls.push("deploy-mark");
        if (m.extractZoneId === z.zoneId) cls.push("extract-mark");
        if ((m.captureZoneIds || []).includes(z.zoneId)) cls.push("capture-mark");
        const inOps = zoneInOps(plan.mapId, z);
        if (!inOps) cls.push("fog");
        const recruitHere = wildRecruitAtZone(plan.mapId, z.zoneId);
        const ambientHere = null; // Only the mission's reported recruit belongs on the tactical map.
        if (recruitHere) cls.push("has-recruit");
        else if (ambientHere) cls.push("has-recruit-ambient");
        const chip = recruitHere
          ? `<div class="zone-chip">rez</div>`
          : ((intel.openTarget || intel.preferred) ? `<div class="zone-chip">open</div>` : "");
        const recruitTitle = recruitHere
          ? ` · THIS DROP wreck: ${recruitHere.name || recruitHere.id}`
          : (ambientHere
            ? ` · home pad ${ambientHere.name || ambientHere.id} (mark target/infil to seed)`
            : "");
        const fogNote = inOps ? "" : " · outside ops";
        return `<div role="button" tabindex="0" class="${cls.join(" ")}" data-zone="${esc(z.zoneId)}"
          style="left:${left}%;top:${top}%;width:${w}%;height:${h}%"
          title="${esc(z.label || z.zoneId)}${intel.control ? " · " + intel.control : ""}${esc(recruitTitle)}${fogNote}">
          <div class="zone-label">${esc(z.label || z.zoneId)}</div>${chip}
        </div>`;
      }).join("");
      el.querySelectorAll(".zone").forEach(z => {
        z.onclick = () => markZone(z.dataset.zone);
        z.onkeydown = ev => { if(ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); z.click(); } };
      });
      drawRouteArrows(plan, zones);
    }
    const m = plan.marks || {};
    const zoneName = (id) => {
      if (!id) return "—";
      const z = zones.find(x => x.zoneId === id);
      return (z && z.label) || id;
    };
    const modeLabel = ({ capture: "objective", deploy: "landing", extract: "extraction" })[state.markMode] || state.markMode;
    const opsLit = zones.filter(z => zoneInOps(plan.mapId, z)).length;
    $("marks-sum").innerHTML =
      `<b>Landing</b> ${esc(zoneName(m.deployZoneId))} · <b>Target</b> ${(m.captureZoneIds || []).map(z => esc(zoneName(z))).join(", ") || "—"} · <b>Extraction</b> ${esc(zoneName(m.extractZoneId))}<br>` +
      `route arrows · marking <b>${esc(modeLabel)}</b> · ops ${opsLit}/${zones.length || 0} zones · quiet rim or Ashwalker base`;
    updateDeployGate();
  }

  function markZone(zoneId) {
    const plan = state.plan;
    if (!plan) return;
    const board = BOARDS[plan.mapId] || {};
    const z = (board.zones || []).find(x => x.zoneId === zoneId);
    const m = plan.marks;
    if (state.markMode === "deploy" || state.markMode === "extract") {
      if (plan.wetReach) {
        toast("These doors are the sortie. Pick another card to head a different way.", "err");
        return;
      }
      if (!z || !isLegalLanding(plan.mapId, z)) {
        toast("Establish an Ashwalker foothold here to use this landing area, or choose a legal quiet perimeter.", "err");
        return;
      }
      if (state.markMode === "deploy") {
        m.deployZoneId = zoneId;
        if (!m.extractZoneId) m.extractZoneId = zoneId;
      } else {
        m.extractZoneId = zoneId;
      }
    } else {
      // Target is a different mark type from landing
      const caps = m.captureZoneIds || [];
      const i = caps.indexOf(zoneId);
      if (i >= 0) caps.splice(i, 1);
      else {
        if (caps.length >= (plan.maxCaptureMarks || 1)) caps.shift();
        caps.push(zoneId);
      }
      m.captureZoneIds = caps;
    }
    // Always track the last clicked zone for the company recruit tease.
    state.selectedZoneId = zoneId;
    renderBoard();
    renderCompany();
    const seeded = wildRecruitAtZone(plan.mapId, zoneId);
    if (seeded) {
      toast(`This Drop seeds wreck · ${seeded.name || seeded.id}`, "ok");
    } else {
      const ambient = null; // Unobserved recruit homes are not battlefield intelligence.
      if (ambient) {
        toast(`${ambient.name || ambient.id} homes here — mark as target/infil to seed their wreck`, "ok");
      }
    }
  }

  function downloadJson(filename, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1500);
  }

  function authoredPads(plan) {
    const ch = ((state.hub.node || {}).choices || []).find(c => c && c.id === (plan && plan.choiceId));
    const e = (ch && ch.effect) || {};
    return new Set([
      e.preferredDeployZoneId, e.deploymentZoneId,
      e.preferredExtractionZoneId, e.extractionZoneId,
      e.infilZoneId, e.exfilZoneId,
    ].filter(Boolean).map(String));
  }
  function canLaunchFrom(plan, z) {
    if (!z) return false;
    if (isLegalLanding(plan.mapId, z)) return true;
    // Recommended sorties stamp their own infil. The client used to reject
    // those pads and hide the toast under this dialog, so Confirm did nothing.
    return authoredPads(plan).has(String(z.zoneId));
  }
  function blockDrop(msg) {
    toast(msg, "err");
    const body = $("drop-confirm-body");
    if (body) {
      const base = body.getAttribute("data-route") || body.innerHTML;
      body.innerHTML = base + `<br><b style="color:var(--bad)">${esc(msg)}</b>`;
    }
    const el = $("drop-confirm");
    if (el) el.classList.add("show");
  }

  async function commitDeploy(launch) {
    const plan = state.plan;
    if (!plan) return blockDrop("Pick a sortie on the map first");
    if (!companySealed()) {
      return blockDrop("Form the company first — pick 3 packs and Confirm");
    }
    if (state.dropping) return;
    // Drop roster = packs marked Dropping. Core is added server-side and here.
    plan.crewBand = droppingPackIds();
    plan.deployAces = sealedDeployAces();
    if (!(plan.marks && plan.marks.captureZoneIds && plan.marks.captureZoneIds.length)) {
      return blockDrop("Mark a target (wound) on the map first");
    }
    if (!plan.marks.deployZoneId) {
      return blockDrop("Mark an infil pad first");
    }
    const board = BOARDS[plan.mapId] || {};
    const zones = board.zones || [];
    const dep = zones.find(z => z.zoneId === plan.marks.deployZoneId);
    const ext = zones.find(z => z.zoneId === (plan.marks.extractZoneId || plan.marks.deployZoneId));
    if (!dep || !canLaunchFrom(plan, dep)) {
      return blockDrop("Infil must be a quiet rim, an Ashwalker base, or this sortie's pad");
    }
    if (ext && !canLaunchFrom(plan, ext)) {
      return blockDrop("Exfil must be a quiet rim, an Ashwalker base, or this sortie's pad");
    }
    plan.commerceDeploy = { tenebrium: commerce().tenebrium, kit: commerce().deployKit || [] };

    if (state.dropping || (state.warm && (state.warm.phase === "loading" || state.warm.phase === "sealing" || state.warm.phase === "up"))) {
      paintWarmStatus();
      return;
    }
    const sheet = $("drop-confirm");
    if (sheet) sheet.classList.add("show");
    state.dropping = true;
    state.warm.locked = true;
    state.warm.phase = "loading";
    state.warm.startedAt = Date.now();
    state.warm.rosterToken = "";
    state.warm.rosterSeq = 0;
    renderDropSquad();
    paintWarmStatus();
    updateDeployGate();

    if (state.hostLive) {
      try {
        toast(launch ? "Dropping… The company is locked." : "Sealing the drop…");
        const q = launch ? "?launch=1" : "";
        const res = await fetch(api("/api/deploy" + q), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(plan),
        });
        const data = await res.json().catch(() => ({}));
        const accepted = !!(data && data.accepted);
        const launched = !!(data.launch && data.launch.ok && !data.launch.skipped);
        const reason = (data && (data.error || data.reason || (data.launch && data.launch.reason))) || "";
        if (!accepted && !launched) {
          state.warm.locked = false;
          state.warm.phase = "failed";
          const err = reason || `Drop failed (${res.status})`;
          logLine(err);
          paintWarmStatus(err);
          blockDrop(err);
          return;
        }
        logLine(`Loading ${prettyMap(plan.mapId)}. Recoil will open when the level is ready.`);
        state.hub.flags = state.hub.flags || {};
        state.hub.flags.deployStub = false;
        state.hub.lastResult = { kind: "deploy_committed", at: new Date().toISOString(), seedHint: data.seedHint };
        renderBadges();
        const ns = $("ns-title");
        const nb = $("ns-body");
        if (ns && nb) {
          ns.textContent = "Dropping…";
          nb.innerHTML = `The company is locked. The level is loading with that roster. ` +
            `When the match ends, the <b>bridge brings it home</b>.`;
        }
        pollWarm();
      } catch (e) {
        state.warm.locked = false;
        state.warm.phase = "failed";
        paintWarmStatus("Wire error: " + e.message);
        blockDrop("Wire error: " + e.message);
      } finally {
        state.dropping = false;
        updateDeployGate();
        renderDropSquad();
      }
      return;
    }

    state.dropping = false;
    state.warm.locked = false;
    state.warm.phase = "idle";
    // Offline map-only: download plan, guide player to PLAY_CAMPAIGN
    try {
      downloadJson("hub_deploy_plan.json", plan);
      logLine(`Map-only plan for ${prettyMap(plan.mapId)}. Run PLAY.bat to fight.`);
      toast("Map only — run PLAY.bat to open the wire and drop for real.", "err");
      const ov = $("deploy-overlay");
      if (ov) ov.classList.remove("show");
      state.hub.lastResult = { kind: "deploy_stub", mapId: plan.mapId, contractKind: plan.contractKind };
    } finally {
      state.dropping = false;
      updateDeployGate();
    }
  }

  async function probeHost() {
    const candidates = [];
    if (location.protocol === "http:" || location.protocol === "https:") {
      candidates.push(""); // same origin first
    }
    candidates.push("http://127.0.0.1:8770");
    state.hostLive = false;
    state.hostBase = "";
    for (const base of candidates) {
      try {
        const res = await fetch((base || "") + "/api/status", { cache: "no-store" });
        if (!res.ok) continue;
        const data = await res.json();
        if (!(data.schemaVersion && String(data.schemaVersion).indexOf("hub-host") >= 0) &&
            !(data.capabilities && data.capabilities.stamp)) continue;
        state.hostLive = true;
        state.hostBase = base;
        state.hostInfo = data;
        if (state.hub.flags) state.hub.flags.deployStub = false;
        logLine(`Campaign connected (${base || location.origin})`);
        break;
      } catch (_) { /* try next */ }
    }
    if (!state.hostLive && state.hub.flags) state.hub.flags.deployStub = true;
    if (!state.hostLive) {
      logLine("Map only — run PLAY.bat to fight in BAR.");
    }
    renderBadges();
    if (state.hostLive) {
      startResultPoll();
      startFieldPoll();
      pullHubState().catch(() => {});
    }
  }

  function heatColor(v) {
    // v in [0,1] → dark green to gold
    const t = Math.max(0, Math.min(1, v));
    const r = Math.round(20 + t * 200);
    const g = Math.round(40 + t * 160);
    const b = Math.round(30 + t * 40);
    return `rgb(${r},${g},${b})`;
  }

  function buildRho(mapId) {
    const board = BOARDS[mapId];
    const zones = (board && board.zones) || [];
    if (!zones.length) return { labels: [], matrix: [], zones: [] };
    const n = zones.length;
    const centers = zones.map(z => {
      const b = z.bounds || {};
      return {
        x: ((b.xMin || 0) + (b.xMax || 1)) / 2,
        z: ((b.zMin || 0) + (b.zMax || 1)) / 2,
        zone: z,
      };
    });
    const matrix = Array.from({ length: n }, () => Array(n).fill(0));
    const g = state.hub.graph || {};
    const contest = Math.min(1.5, Number(g.q6_contested) || 0.85);
    const voidS = Number(g.q2_void_structure) || 0.15;
    for (let i = 0; i < n; i++) {
      const ctrl = (zones[i].control || zones[i].defaultControl || "neutral");
      const diag = 0.35 + 0.4 * contest * (ctrl === "contested" || ctrl === "armada" ? 1 : 0.6);
      matrix[i][i] = Math.min(1, diag);
      for (let j = i + 1; j < n; j++) {
        const dx = centers[i].x - centers[j].x;
        const dz = centers[i].z - centers[j].z;
        const dist = Math.sqrt(dx * dx + dz * dz) || 0.01;
        let coh = Math.exp(-dist * (2.2 + voidS * 2)) * contest * 0.85;
        if (zones[i].capturable && zones[j].capturable) coh *= 1.15;
        coh = Math.min(0.95, coh);
        matrix[i][j] = coh;
        matrix[j][i] = coh;
      }
    }
    // Normalize row-ish for display
    let mx = 0.001;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) mx = Math.max(mx, matrix[i][j]);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) matrix[i][j] = matrix[i][j] / mx;
    return {
      labels: zones.map(z => (z.label || z.zoneId || "?").slice(0, 10)),
      matrix,
      zones,
      centers,
    };
  }

  function renderQuantum() {
    const mapId = state.focusMap
      || state.hub.sessionHomeMap
      || (state.hub.node && state.hub.node.regionHint)
      || ((state.hub.regions || [])[0] && (state.hub.regions || [])[0].mapId);
    const g = state.hub.graph || {};
    const rhoCamp = state.hub.campaignRho || {};
    const axes = rhoCamp.axes || {};
    const keys = [
      ["Armada↔Cortex", g.q0_armada_cortex],
      ["Void scars", g.q2_void_structure],
      ["Contested", g.q6_contested],
      ["Independents", g.q6_independent],
      ["Scarcity", g.q7_resource_scarcity],
    ];
    if (axes.arm_cor != null) {
      keys.push(["Faction pull", axes.arm_cor], ["Path tilt", axes.phi], ["Tenebrium pressure", axes.tenebrium]);
    }
    $("graph-scalars").innerHTML = keys.map(([k, v]) =>
      `<span class="scalar-pill">${k} <b>${Number(v || 0).toFixed(2)}</b></span>`
    ).join("");
    const sp = state.hub.spectral || {};
    const energy = Number(sp.energy || keys.reduce((s, [, v]) => s + Math.abs(Number(v || 0)), 0));
    const barPct = Math.min(100, Math.round((energy / 6) * 100));
    $("spec-bar").innerHTML = `<i style="width:${barPct}%"></i>`;
    const pur = rhoCamp.purity != null ? Number(rhoCamp.purity).toFixed(2) : "—";
    const ent = rhoCamp.entropy != null ? Number(rhoCamp.entropy).toFixed(2) : "—";
    $("spec-meta").textContent =
      `Theater: ${prettyMap(mapId)} · war energy ${energy.toFixed(2)} · focus ${pur} · chaos ${ent}`;
    const adv = $("rho-advanced");
    if (adv) {
      adv.textContent =
        `q0=${Number(g.q0_armada_cortex||0).toFixed(3)} q2=${Number(g.q2_void_structure||0).toFixed(3)} ` +
        `q6c=${Number(g.q6_contested||0).toFixed(3)} q7=${Number(g.q7_resource_scarcity||0).toFixed(3)} ` +
        `λ=${Number(sp.dominantEigenvalue||0).toFixed(3)} path=${state.hub.pathSignal||"B"}`;
    }

    const rho = buildRho(mapId);
    const n = rho.matrix.length;
    if (!n) {
      $("rho-table").innerHTML = "<tr><td style='color:var(--muted);padding:.4rem'>No zone board — run build_zone_boards_v1.py</td></tr>";
      $("ent-svg").innerHTML = "";
      $("rho-inspect").textContent = "";
      return;
    }
    // Clamp selection
    state.rhoSel.i = Math.min(state.rhoSel.i, n - 1);
    state.rhoSel.j = Math.min(state.rhoSel.j, n - 1);

    let head = "<tr><th></th>" + rho.labels.map(l => `<th title="${esc(l)}">${esc(l.slice(0, 4))}</th>`).join("") + "</tr>";
    let body = "";
    for (let i = 0; i < n; i++) {
      body += `<tr><th title="${esc(rho.labels[i])}">${esc(rho.labels[i].slice(0, 4))}</th>`;
      for (let j = 0; j < n; j++) {
        const v = rho.matrix[i][j];
        const sel = (state.rhoSel.i === i && state.rhoSel.j === j) ? " sel" : "";
        body += `<td class="${sel}" data-i="${i}" data-j="${j}" style="background:${heatColor(v)}" title="${v.toFixed(3)}"></td>`;
      }
      body += "</tr>";
    }
    $("rho-table").innerHTML = head + body;
    $("rho-table").querySelectorAll("td[data-i]").forEach(td => {
      td.onclick = () => {
        state.rhoSel = { i: +td.dataset.i, j: +td.dataset.j };
        renderQuantum();
      };
    });
    const si = state.rhoSel.i, sj = state.rhoSel.j;
    $("rho-inspect").textContent =
      `Link ${rho.matrix[si][sj].toFixed(2)} · ${rho.labels[si]} ↔ ${rho.labels[sj]}`;

    // Entanglement SVG — edges for strong off-diagonals
    const W = 280, H = 140, pad = 18;
    const pts = (rho.centers || []).map((c, idx) => ({
      x: pad + c.x * (W - 2 * pad),
      y: pad + c.z * (H - 2 * pad),
      i: idx,
    }));
    let edges = "";
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const v = rho.matrix[i][j];
        if (v < 0.35) continue;
        edges += `<line x1="${pts[i].x}" y1="${pts[i].y}" x2="${pts[j].x}" y2="${pts[j].y}"
          stroke="rgba(126,200,255,${0.15 + v * 0.7})" stroke-width="${0.6 + v * 2.2}"/>`;
      }
    }
    const nodes = pts.map((p, i) => {
      const hot = i === si || i === sj;
      return `<circle cx="${p.x}" cy="${p.y}" r="${hot ? 5.5 : 3.5}"
        fill="${hot ? "var(--gold)" : "var(--edge)"}" opacity="0.9"/>`;
    }).join("");
    $("ent-svg").innerHTML = edges + nodes;
  }

  function mergeHubPatch(patch) {
    if (!patch) return;
    if (patch.aces) state.hub.aces = patch.aces;
    if (patch.missionNumber != null) {
      state.hub.missionNumber = patch.missionNumber;
      // arc rebuild light
      const n = patch.missionNumber;
      state.hub.arc = n <= 5
        ? { id: 1, title: "First Scar", maxCaptureMarks: 1 }
        : n <= 10
          ? { id: 2, title: "Second Scar", maxCaptureMarks: 2 }
          : { id: 3, title: "Third Scar", maxCaptureMarks: 3 };
    }
    if (patch.reputation) state.hub.reputation = patch.reputation;
    if (patch.graph) state.hub.graph = patch.graph;
    if (patch.graphPressure) state.hub.graphPressure = patch.graphPressure;
    if (patch.collapse) state.hub.lastCollapse = patch.collapse;
    if (patch.spectral) state.hub.spectral = patch.spectral;
    if (patch.node) state.hub.node = patch.node;
    if (patch.lastResult) state.hub.lastResult = patch.lastResult;
    // Post-sortie wallets — must update even when poll skips full pullHubState.
    if (patch.commerce && typeof patch.commerce === "object") {
      state.hub.commerce = Object.assign({}, state.hub.commerce || {}, patch.commerce);
    }
    if (patch.tenebrium != null) {
      state.hub.tenebrium = patch.tenebrium;
      state.hub.commerce = state.hub.commerce || {};
      state.hub.commerce.tenebrium = patch.tenebrium;
    }
    if (patch.factionBanks) state.hub.factionBanks = patch.factionBanks;
    if (patch.company && typeof patch.company === "object") {
      state.hub.company = Object.assign({}, state.hub.company || {}, patch.company);
      // Keep formation mirrors honest with the bag when only tenebrium was patched.
      if (patch.tenebrium != null) state.hub.company.formationWalletTnb = patch.tenebrium;
      if (patch.commerce && patch.commerce.metalK != null) {
        state.hub.company.formationWalletKm = patch.commerce.metalK;
      }
    }
    if (patch.homeEval) state.hub.homeEval = patch.homeEval;
    if (patch.homeCamp) state.hub.homeCamp = patch.homeCamp;
    if (patch.regions && Array.isArray(patch.regions)) {
      const byId = Object.fromEntries(patch.regions.map(r => [r.mapId, r]));
      (state.hub.regions || []).forEach(r => {
        const u = byId[r.mapId];
        if (u && u.control) r.control = u.control;
      });
    }
    if (state.hub.flags) state.hub.flags.deployStub = false;
    const debrief = patch.debrief || (patch.lastResult && patch.lastResult.debrief) || null;
    const tokens = (patch.lastResult && patch.lastResult.tokens) || (debrief && debrief.changed) || [];
    const auto = !!(patch.autoApplied || (patch.lastResult && patch.lastResult.autoApplied));
    const headline = (debrief && debrief.headline)
      || patch.headline
      || (patch.lastResult && patch.lastResult.headline)
      || null;
    const verdict = (debrief && debrief.verdict) || patch.verdict || (patch.lastResult && patch.lastResult.verdict);
    const reasonHint = (debrief && debrief.reasonHint)
      || patch.reasonHint
      || (patch.lastResult && patch.lastResult.reasonHint)
      || "";
    // Rebuild / refresh writes verdict=state_sync — not a real homecoming.
    // Showing it as "RESULT PENDING" (incomplete fallback) confuses the Drop loop.
    const isSyncNoise = !verdict || ["state_sync", "sync", "none"].includes(String(verdict).toLowerCase());
    if (!isSyncNoise && (headline || tokens.length || auto || verdict)) {
      const prefix = auto ? "Bridge: " : (verdict === "incomplete" ? "Incomplete: " : "Brought home: ");
      logLine(prefix + (headline || tokens.slice(0, 8).join(" · ") || "campaign advanced"));
      const collapseChips = (debrief && debrief.collapse && debrief.collapse.chips)
        || (patch.collapse && patch.collapse.chips)
        || [];
      const chips = [];
      const seen = new Set();
      [...tokens, ...collapseChips].forEach((c) => {
        const s = String(c || "");
        if (!s || seen.has(s)) return;
        seen.add(s);
        chips.push(s);
      });
      showHomecoming({
        verdict: verdict || "incomplete",
        banner: (debrief && debrief.banner) || patch.banner,
        headline: headline,
        reasonHint: reasonHint || "Review the return ledger for confirmed changes.",
        chips: chips.slice(0, 12),
      });
      if (verdict === "incomplete") {
        toast(headline || "Result not home — retry bring-home or Abandon", "err");
      } else if (verdict === "abandon") {
        toast(headline || "Left the field — mark the next board", "warn");
      } else if (debrief && debrief.duplicate) {
        toast("Already applied — state unchanged", "ok");
      } else {
        toast(auto
          ? (headline || "Bridge brought the sortie home")
          : (headline || "The ashes keep score — company and map updated"), "ok");
      }
    } else if (isSyncNoise && tokens.length) {
      logLine("Map synced · " + tokens.slice(0, 6).join(" · "));
    }
    renderBadges();
    renderAces();
    renderRegions();
    renderShop();
    renderNode();
    renderMapPicker();
    renderQuantum();
  }

  async function pullHubState() {
    if (!state.hostLive) return;
    const res = await fetch(api("/api/hub-state"), { cache: "no-store" });
    const j = await res.json();
    if (j.ok && j.hub) {
      const focus = state.focusMap;
      state.hub = j.hub;
      state.focusMap = focus || j.hub.sessionHomeMap || (j.hub.node && j.hub.node.regionHint);
      ensureFocusMapAvailable();
      if (state.hub.flags) state.hub.flags.deployStub = false;
      syncCrewFromHub();
      renderBadges();
      renderAces();
      renderRegions();
      renderShop();
      renderMuster();
      renderNode();
      renderQuantum();
      refreshTheaterForFocus();
      // Re-open formation picker if a refresh left us unsealed without the modal.
      syncCompanyIntroGate();
      logLine("Map refreshed from the living campaign");
    }
  }

  async function pullBarResult() {
    if (!state.hostLive) {
      return toast("Open the wire first — run PLAY.bat", "err");
    }
    toast("Listening for the last sortie…");
    try {
      const res = await fetch(api("/api/advance?extract=1"), { method: "POST" });
      const j = await res.json().catch(() => ({}));
      const rr = await fetch(api("/api/result"), { cache: "no-store" });
      const rj = await rr.json().catch(() => ({}));
      if (rj.present && rj.result) {
        state.lastResultAt = rj.result.at;
        mergeHubPatch({
          ...rj.result,
          debrief: j.debrief || rj.result.debrief,
          headline: j.headline || rj.result.headline,
          verdict: j.verdict || rj.result.verdict,
        });
      } else if (j.debrief || (j.apply && j.apply.lastResult) || j.incomplete) {
        mergeHubPatch({
          lastResult: (j.apply && j.apply.lastResult) || j.lastResult,
          debrief: j.debrief,
          headline: j.headline,
          verdict: j.verdict,
          missionNumber: j.apply && j.apply.missionNumber,
          tenebrium: j.tenebrium || (j.apply && j.apply.tenebrium),
          commerce: j.commerce || (j.apply && j.apply.commerce),
          company: j.company || (j.apply && j.apply.company),
          factionBanks: j.factionBanks || (j.apply && j.apply.factionBanks),
        });
      } else if (!j.ok) {
        toast((j.error || (j.apply && j.apply.error) || "Nothing to bring home yet — finish a match or Abandon"), "err");
        return;
      }
      // Always re-pull hub SoT so Tnb / km$ badges match campaign_state.
      await pullHubState();
      if (!(rj.present && rj.result) && !(j.debrief || (j.apply && j.apply.lastResult) || j.incomplete)) {
        toast("Map refreshed — no new scars this pass", "ok");
      }
    } catch (e) {
      toast("Could not bring it home: " + e.message, "err");
    }
  }

  async function abandonSortie() {
    if (!state.hostLive) {
      return toast("Open the wire first — run PLAY.bat", "err");
    }
    if (!confirm("Abandon this sortie? No zone flip, no fake win. Next Drop unlocks.")) return;
    try {
      const res = await fetch(api("/api/abandon"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "player_abandon" }),
      });
      const j = await res.json().catch(() => ({}));
      if (j.ok || j.abandon) {
        mergeHubPatch({
          debrief: j.debrief,
          headline: j.headline || "Withdrawn.",
          verdict: "abandon",
          lastResult: { verdict: "abandon", debrief: j.debrief, at: j.at },
        });
        await pullHubState();
      } else {
        toast(j.error || "Abandon failed", "err");
      }
    } catch (e) {
      toast("Abandon failed: " + e.message, "err");
    }
  }

  async function resetCampaign() {
    if (!state.hostLive) {
      return toast("Open the wire first — or run RESET.bat from the workspace", "err");
    }
    const typed = window.prompt(
      "FULL RESET (same as RESET.bat):\n" +
        "• backup then wipe campaign_state\n" +
        "• archive stale inbox/outbox results\n" +
        "• clear Act-N mission lua (stops naked-com ghosts)\n" +
        "• fresh mission 1 + starter Punch, metal 0×1km$\n\n" +
        "Type YES to confirm:",
      ""
    );
    if (!typed || String(typed).trim().toUpperCase() !== "YES") {
      return toast("Reset cancelled", "err");
    }
    try {
      toast("Resetting campaign…");
      const res = await fetch(api("/api/reset-campaign"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: "YES" }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok || j.ok === false) {
        const detail = (j && (j.error || (j.reset && j.reset.error))) || "Reset failed";
        return toast(detail, "err");
      }
      state.crewBand = [];
      state.sortieSynced = false;
      state.knownCompanyIds = null;
      state.selectedZoneId = null;
      await pullHubState();
      syncCrewFromHub();
      renderCompany();
      showCompanyIntro();
      const mn = (j && j.missionNumber) || (state.hub && state.hub.missionNumber) || 1;
      logLine("Campaign reset — mission " + mn + ". Form the company (pick 3 packs) before Drop.");
      toast("Campaign reset — pick your company to continue.", "ok");
    } catch (e) {
      toast("Reset failed: " + e.message, "err");
    }
  }

  async function fetchSaveList() {
    const res = await fetch(api("/api/saves"), { cache: "no-store" });
    const j = await res.json().catch(() => ({}));
    if (!res.ok || j.ok === false) {
      throw new Error((j && j.error) || "Could not list saves");
    }
    return j.saves || [];
  }

  async function saveCampaign() {
    if (!state.hostLive) {
      return toast("Open the wire first (PLAY.bat / kernel on :8770)", "err");
    }
    const mn = (state.hub && state.hub.missionNumber) || 1;
    const suggested = "mission_" + mn;
    const name = window.prompt(
      "Save campaign state to a named slot (state/saves/<name>/).\n" +
        "Letters, numbers, dash, underscore. Leave blank for a timestamped slot.",
      suggested
    );
    if (name === null) return toast("Save cancelled", "err");
    try {
      toast("Saving…");
      const res = await fetch(api("/api/save-campaign"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: String(name || "").trim(), label: String(name || "").trim() }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok || j.ok === false) {
        return toast((j && j.error) || "Save failed", "err");
      }
      const slot = (j && j.slot) || name || "?";
      logLine("Saved campaign → slot " + slot + " (mission " + ((j.meta && j.meta.missionNumber) || mn) + ")");
      toast("Saved as “" + slot + "”", "ok");
    } catch (e) {
      toast("Save failed: " + e.message, "err");
    }
  }

  async function loadCampaign() {
    if (!state.hostLive) {
      return toast("Open the wire first (PLAY.bat / kernel on :8770)", "err");
    }
    let saves = [];
    try {
      saves = await fetchSaveList();
    } catch (e) {
      return toast(e.message || "Could not list saves", "err");
    }
    if (!saves.length) {
      return toast("No saves yet — hit Save first", "err");
    }
    const listing = saves
      .map((s, i) => {
        const when = s.savedAt ? String(s.savedAt).replace("T", " ").replace("Z", "") : "?";
        return (i + 1) + ") " + (s.label || s.id) + "  ·  m" + (s.missionNumber ?? "?") + "  ·  " + when;
      })
      .join("\n");
    const pick = window.prompt(
      "Load a save slot (overwrites live campaign_state; current state is backed up first).\n\n" +
        listing +
        "\n\nType the slot name (or number):",
      saves[0].id
    );
    if (pick === null) return toast("Load cancelled", "err");
    let slot = String(pick || "").trim();
    const asNum = Number(slot);
    if (Number.isInteger(asNum) && asNum >= 1 && asNum <= saves.length) {
      slot = saves[asNum - 1].id;
    }
    if (!slot) return toast("No slot chosen", "err");
    const typed = window.prompt(
      "Load “" + slot + "” over the live campaign?\nType YES to confirm:",
      ""
    );
    if (!typed || String(typed).trim().toUpperCase() !== "YES") {
      return toast("Load cancelled", "err");
    }
    try {
      toast("Loading “" + slot + "”…");
      const res = await fetch(api("/api/load-campaign"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot, confirm: "YES" }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok || j.ok === false) {
        return toast((j && j.error) || "Load failed", "err");
      }
      state.crewBand = [];
      state.sortieSynced = false;
      state.knownCompanyIds = null;
      state.selectedZoneId = null;
      await pullHubState();
      syncCrewFromHub();
      renderCompany();
      if (!companySealed()) showCompanyIntro();
      else hideCompanyIntro();
      const mn = (j && j.missionNumber) || (state.hub && state.hub.missionNumber) || "?";
      logLine("Loaded save “" + slot + "” → mission " + mn);
      toast(
        companySealed()
          ? ("Loaded “" + slot + "” — company intact.")
          : ("Loaded “" + slot + "” — form the company before Drop."),
        "ok"
      );
    } catch (e) {
      toast("Load failed: " + e.message, "err");
    }
  }

  function showCoach(force) {
    try {
      if (!force && localStorage.getItem("va_coach_seen_v2") === "1") return;
    } catch (_) { /* private mode */ }
    $("coach").classList.add("show");
  }
  function hideCoach(remember) {
    $("coach").classList.remove("show");
    if (remember) {
      try { localStorage.setItem("va_coach_seen_v2", "1"); } catch (_) { /* */ }
    }
  }

  function startResultPoll() {
    if (startResultPoll._on) return;
    startResultPoll._on = true;
    setInterval(async () => {
      if (!state.hostLive) return;
      try {
        const rr = await fetch(api("/api/result"), { cache: "no-store" });
        const rj = await rr.json();
        if (rj.present && rj.result && rj.result.at && rj.result.at !== state.lastResultAt) {
          state.lastResultAt = rj.result.at;
          // Phase 2: bridge may set autoApplied on hub_result
          mergeHubPatch({
            ...rj.result,
            autoApplied: !!(rj.result.autoApplied),
            lastResult: rj.result.lastResult || rj.result,
          });
          // Full hub pull so Tnb/km$ cannot lag behind the debrief card.
          await pullHubState();
        }
      } catch (_) { /* host down */ }
    }, 8000);
  }

  // Pass five: there is no "BAR paused on the map" state any more. The sortie ends on the
  // manifest in BAR; the kernel brings the result home; the debrief arrives through /api/result.
  function startFieldPoll() { /* retired */ }

  // Tabs
  document.querySelectorAll(".tab").forEach(tab => {
    tab.onclick = () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t === tab));
      const name = tab.dataset.tab;
      $("panel-shop").hidden = name !== "shop";
      $("panel-theaters").hidden = name !== "theaters";
      $("panel-manifold").hidden = name !== "manifold";
      if (name === "manifold") renderQuantum();
    };
  });

  document.querySelectorAll(".mode-btn").forEach(btn => {
    btn.onclick = () => {
      state.markMode = btn.dataset.mode;
      document.querySelectorAll(".mode-btn").forEach(b => b.classList.toggle("active", b === btn));
      renderBoard();
    };
  });

  if ($("btn-clear-marks")) {
    $("btn-clear-marks").onclick = () => {
      if (!state.plan) return;
      state.plan.marks = defaultMarks(state.plan.mapId);
      renderBoard();
      toast("Route reset", "ok");
    };
  }
  $("btn-deploy").onclick = () => showDropConfirm();
  if ($("drop-confirm-cancel")) $("drop-confirm-cancel").onclick = () => hideDropConfirm();
  if ($("drop-confirm-go")) $("drop-confirm-go").onclick = () => onDropConfirmGo();
  const dropConfirmEl = $("drop-confirm");
  if (dropConfirmEl) {
    dropConfirmEl.addEventListener("click", (ev) => {
      if (ev.target === dropConfirmEl) hideDropConfirm();
    });
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      hideDropConfirm();
      hideCampSheet();
    }
  });
  if ($("camp-chip")) $("camp-chip").onclick = () => showCampSheet();
  if ($("btn-camp-raise")) $("btn-camp-raise").onclick = () => raiseCampFromSheet();
  if ($("btn-camp-founding")) $("btn-camp-founding").onclick = () => openFoundingSortieFromCamp();
  if ($("btn-camp-broker")) $("btn-camp-broker").onclick = () => openBrokerFromCamp();
  if ($("btn-camp-close")) $("btn-camp-close").onclick = () => hideCampSheet();
  if ($("btn-hearth-confirm")) $("btn-hearth-confirm").onclick = () => confirmHearthTalk();
  if ($("btn-hearth-cancel")) $("btn-hearth-cancel").onclick = () => cancelHearthTalk();
  const campSheetEl = $("camp-sheet");
  if (campSheetEl) {
    campSheetEl.addEventListener("click", (ev) => {
      if (ev.target === campSheetEl) hideCampSheet();
    });
  }
  window.addEventListener("resize", () => {
    if (campSheetEl && campSheetEl.classList.contains("show")) pinCampSheetToCompanyBar();
  });
  if ($("btn-seal-company")) $("btn-seal-company").onclick = () => sealCompany();
  if ($("btn-seal-company-intro")) $("btn-seal-company-intro").onclick = () => sealCompany();
  if ($("btn-open-company-intro")) {
    $("btn-open-company-intro").onclick = () => {
      showCompanyIntro();
      toast("Pick 3 packs, then Confirm company", "ok");
    };
  }
  if ($("btn-bro-tzar")) $("btn-bro-tzar").onclick = () => orderBroTzar();
  $("btn-pull-result").onclick = () => pullBarResult();
  if ($("btn-abandon")) $("btn-abandon").onclick = () => abandonSortie();
  if ($("btn-reset-campaign")) $("btn-reset-campaign").onclick = () => resetCampaign();
  if ($("btn-save-campaign")) $("btn-save-campaign").onclick = () => saveCampaign();
  if ($("btn-load-campaign")) $("btn-load-campaign").onclick = () => loadCampaign();
  if ($("hc-dismiss")) $("hc-dismiss").onclick = () => hideHomecoming();
  $("btn-sync-hub").onclick = async () => {
    if (!state.hostLive) return toast("Run PLAY.bat for a live map", "err");
    try {
      await fetch(api("/api/rebuild-hub"), { method: "POST" });
      await pullHubState();
      toast("Map refreshed", "ok");
    } catch (e) {
      toast("Refresh failed: " + e.message, "err");
    }
  };
  $("btn-help").onclick = () => showCoach(true);
  $("coach-go").onclick = () => hideCoach(true);
  $("coach-skip").onclick = () => hideCoach(true);


  // Narrow adapter for the command console. Deployment still uses the established pipeline.
  window.Verdance = {
    snapshot: () => ({hub:state.hub, plan:state.plan, focusMap:state.focusMap, live:state.hostLive}),
    selectOperation: id => onChoice(id),
    focusMap: id => { state.focusMap=id; renderNode(); refreshTheaterForFocus(); },
    refresh: pullHubState,
    api,
    notify: toast,
    showCamp: showCampSheet,
    renderCamp: renderCampSheet,
    recommendCompany: () => {
      if (companySealed()) return;
      const pool=crewBandOrder().filter(id => !crewCoreIds().includes(id) && !['dead','lost'].includes(String(aceById(id)?.status || 'active')));
      const priorities=['solarium','vane','volt','hearth','consul','warder'];
      const ordered=[...priorities.filter(id=>pool.includes(id)),...pool.filter(id=>!priorities.includes(id))];
      const selected=[]; let budget=crewWallet(); let metal=crewMetalK();
      for(const id of ordered) {
        if(selected.length>=crewSeatCap()) break;
        const cost=crewHireCost(id); const metalCost=Number(crewPack(id)?.hireKm || 0); if(cost>budget || metalCost>metal) continue;
        selected.push(id); budget-=cost; metal-=metalCost;
      }
      if(selected.length!==crewSeatCap()) return toast('No affordable complete recommendation. Choose packs individually.','warn');
      state.crewBand=selected; renderCompany(); renderCompanyIntro();
      toast('Suggested company selected. Review and edit before confirming.','ok');
    },
    companyMemberIds: () => [...new Set([...crewCoreIds(), ...(companySealed()?companyOwnedBand():state.crewBand)])],
    companyRecommendation: () => crewBandOrder().filter(heroIsDeployable),
  };

  // Boot
  if (!window.HUB_STATE) {
    $("title").textContent = "The map is blank";
    $("voice").textContent = "Rebuild the hub (build_hub_state_v1.py), then open this again.";
    return;
  }
  // Prefer the recommended sortie theater (often Greenest Fields) over home ground
  // so the briefing table matches the primary Drop — home stays on the badge.
  state.focusMap =
    (H.node && (H.node.sortieMapId || H.node.regionHint)) ||
    H.sessionHomeMap ||
    (H.regions && H.regions[0] && H.regions[0].mapId) ||
    "greenest_fields";
  ensureFocusMapAvailable();
  renderBadges();
  renderRegions();
  renderShop();
  renderNode();
  renderQuantum();
  refreshTheaterForFocus(); // also renderCompany via theater refresh
  renderCompany();
  logLine(
    `The map answers · home ${prettyMap(H.sessionHomeMap || "the_rock_jungle")} · ` +
    `ops ${prettyMap(state.focusMap)} · ${availableMaps().length} maps · ${(commerce().shop||[]).length} broker listings`
  );
  probeHost();
  // First open: company intro owns formation. Coach waits until the company is sealed.
  // Defer one tick so a racing pullHubState cannot leave the picker hidden.
  setTimeout(() => {
    if (!companySealed()) showCompanyIntro();
  }, 0);
})();

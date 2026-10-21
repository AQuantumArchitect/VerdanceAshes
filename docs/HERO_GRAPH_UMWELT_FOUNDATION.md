# Hero Graph · Umwelt Foundation

**Status:** living foundation (not G0 ship work).  
**SSOT molecules:** `data/story/hero_umwelt.json`  
**SSOT edges:** `data/story/support_web.json`  
**Analyzer:** retired in pass 10 (hero_graph_analyze); the live lane is `tools/verdance/company/hero_observe.py`  
**Classical rhyme:** [bar-eco-manifold](https://bar-eco-manifold-five.vercel.app/) · campaign design § eco → quantum  
**World vs cast:** this file is **character graph H**. World graph G + Drop-as-collapse: [`GRAPH_COLLAPSE_SSOT.md`](GRAPH_COLLAPSE_SSOT.md). Molecules color combat temperament; they are **not** zone ownership.

---

## 0. What this is for

Deep AI aspiration, stated plainly:

1. **Comprehend** the cast as an umwelt field (carriers of significance), not a roster list.
2. Let the **hero graph co-evolve** (parametric cultivation + play evidence).
3. As people play, **observe** how heroes interact with **map-graphs**.
4. Eventually fit a **tensor layer** that approximates “what this hero does on this map pressure” — the same *shape* as eco-manifold candidate ranking, lifted into story/AI disposition.

This doc is the foundation so we don’t densify a second brain. We extend the face we already have. Homecoming may update bonds/XP on H; only `process_result` collapses world G.

---

## 1. Eco-manifold scouting (classical selection logic)

App: `https://bar-eco-manifold-five.vercel.app/` — **ROI Manifold** (industrial structure payback).

### What it actually does

Given **map conditions** `{ wind, tidal, spotValue }` and a **base eco state** (M/s, E/s, storage, BP), it ranks build **candidates** by simulating a short horizon and scoring:

| Symbol | Role |
|--------|------|
| `metalToEnergy` | **70** (same unit rhyme as Verdance ENERGY_PER_METAL) |
| `horizonSeconds` | **300** default planning window |
| `simplePaybackSeconds` | costEV / deltaIncomeEV (∞ if no income under map) |
| **`netHorizonEV`** | primary rank key = incomeΔEV + terminal-stateΔEV − costEV |
| labels | `factory-bp` · `build-power` · `storage` · `geo-transition` · `strategic` · `bad` |

Income model sketch:

- Mex: `metalIncome = xm * spotValue`
- Variable energy: wind / tidal from map sliders; fixed `o` otherwise
- Cost EV: `m * metalToEnergy + e`
- Waterfall sim ticks construction, stalls, overflow, capacity deltas (BP / storage)

**Selection law:** under *this* map state, which structure maximizes net value before the horizon closes?

### Campaign bridge (already designed)

`BAR_verdant_ashes_campaign/` treats the eco manifold as the **classical limit** of the quantum campaign graph:

- Zone biome modifiers (`spotMult`, `windMult`, `eBuildPenalty`, `bpMult`) → `effectiveState`
- Quantum ρ partial-trace → AI **disposition** → eco aggression / build frame / unit preference
- Battles = measurements; between battles the world evolves

Hero work should rhyme with that bridge — **not fork it**.

---

## 2. Comprehending the hero map as umwelt

Each hero is a **molecule**: a vector on ten axes in `[-1, +1]`:

`energy · offense · mobility · sight · pad · craft · heat · fog · sky · ledger`

These are Uexküll **carriers of significance** — what that self-world cares about — not stats.  
Edges in the support web are cultivated when molecules **complement** or **mirror** (with authored seeds only for story pins). Energy links must cultivate (`supply meets hunger`), not be forced.

### Geometry the analyzer sees (35 heroes · 64 edges)

**Principal axes of the cast**

| PC | λ (approx) | Meaning |
|----|------------|---------|
| **PC1** | ~1.12 | **mobility ↔ pad** — kite vs hold / stay meets stride |
| **PC2** | ~0.70 | **offense ↔ energy/craft** — push vs refuse / kiln vs hearth |
| **PC3** | ~0.20 | **fog/sight/pad ↔ craft/energy** — recon-siege vs eco |

PC1 extremes:

- **Stay / pad:** Lumen, Hearth, Warder, Nox, Anvil, Solarium  
- **Stride / kite:** Yeva, Verse, Vane, Stride, Ceil, Kit  

That is the cast’s dominant drama line. ~28/64 support edges already *cross* the mobility/pad divide — mostly `tension` / `friction`, which is healthy.

**PC2 / energy drama (cultivated, working)**

- Hearth↔Kiln (`brakhov`): motif **`supply meets hunger`**, energy complement strength high, polarity `bond`
- Hearth also bonds Bro / Fatboy on the same motif
- Fatboy↔Lumen: `attract` with energy+offense complements (`push meets refuse`)

So the umwelt cultivation path already produces the eco-heart ↔ heat-hunger couple without an authored force seed.

**PC3 / siege↔spotter (cultivated):** pad-heavy stay faces cross-couple with sight/fog recon via motif **`spot meets siege`** — soft boost + sort tie-break + motif lock, same law as energy, no authored seeds. Eyes for the wall. ~20 edges in the live web after cultivation (Anvil↔Volt/Yeva, Warder↔Commando, Nox↔Veil/Spoke/Vale, Grath/Halq/Odessa/Rusk↔Yeva/Spoke/Veil, eco-pad↔Noctua/Tick/Spoke, …).

### Relationship → AI augments (wishlist)

Hearth talks are not only flavor — high pair-bond can soft-bias in-Drop micro later:

| Idea | Example |
|------|---------|
| **Knock cadence** | Volt/Yeva learn Fatboy/Tzar splash timing — dodge friendly arty cones |
| **Eyes for the wall** | Spotter marks bias Anvil/Warder/Kiln push targets |
| **Same circle, different tooth** | Commando mines the Warder annulus; exits stay clean |
| **Feed the roast** | Hearth surplus tempo-holds Kiln hunger on energy drought |

SSOT wishlist: `data/story/support_ai_augments.json`. Law: soft bias only, co-deploy + bond gate, human seal before combat retune, no densify.

### Interesting analytical findings

1. **Near-clones:** `rusk` ≡ `odessa` molecules — same glyph. Graph treats them as interchangeable umwelt; story must carry the difference or we diverge their axes.
2. **Degree-cap pressure:** maxDegree=5 still drops some high-chemistry pairs (e.g. Anvil↔Veil may lose to Anvil↔Volt). Play observe should promote gaps later.
3. **Complement gaps:** Lumen/Hearth vs Vane/Stride/Verse/Ceil/Kit score huge complement but many pairs lack edges — again degree/top-k, not zero affinity. Co-evolution should prefer **play evidence** to promote these over weaker mirrors.
4. **Mirror pile-up:** Cauter≈Quill, Grath≈Halq, Solarium≈Twitch, Tick≈Veil — twin umwelt. Good for rivalry/sibling motifs; bad if every mirror fights for the same five slots.
5. **Axis coverage holes**
   - `heat`: only Brakhov + Mira strong+
   - `sky`: Ceil, Kettle, Noctua
   - `ledger`: many soft +0.4…+0.45 marks, **zero** at \|v\|≥0.5 — axis is under-expressed
   - `sight` / `fog` / `craft`: one-sided (no strong negatives)
6. **Polarity diet:** tension 26 · bond 10 · mirror 8 · attract 8 · friction 8 — tension-heavy (fits PC1). Mentor/rivalry almost unused.
7. **Hero × map fit already ranks like eco candidates**

| Map pressure | Top fits (umwelt · pressure) |
|--------------|------------------------------|
| pad_fortress | Anvil, Rusk, Odessa, Warder |
| fog_siege | Veil, Vale, Tick, Noctua |
| sky_raid | Ceil, Noctua, Yeva, Volt |
| kiln_heat | Brakhov, Mira, Fatboy, Bro |
| hearth_eco | Lumen, Hearth, Solarium, Twitch |
| ledger_raid | Verse, Veil, Spoke, Auditor |

This is the classical limit for heroes: **same question as ROI Manifold**, different candidate set (“which ace pays back on this theater?”).

---

## 3. Layer cake toward the tensor (do in order)

Keep each layer honest and η-tagged. Dark > silent fake-live.

```
L0  Hero molecules          (shipped)     u_h ∈ R^10
L1  Support / couple graph  (shipped)     E ⊂ H×H with umwelt couples
L2  Map-graph pressure      (shipped)     m_z ∈ R^10  (seven maps + sparse zones)
L3  Play observe stamps     (shipped)     JSONL: deploy, bond, outcome, zone
L4  Tensor approximation    (later)       T[h, map_axis, outcome] / low-rank
L5  Disposition read        (later)       soft rank / bark / AI bias — no densify
```

### L2 — Map pressure as umwelt (**shipped**)

SSOT: `data/story/map_umwelt.json` · loader: `tools/map_umwelt_v1.py`

Seven live pool maps each carry:
- `ecoBridge` `{spotMult, windMult, eBuildPenalty, bpMult}` — classical ROI rhyme
- `mapPressure` on the ten hero axes
- sparse `zones{}` deltas (opening pads / vaults / home spillway)

```bash
python tools/map_umwelt_v1.py list
python tools/map_umwelt_v1.py fit --map eye_of_horus
python tools/map_umwelt_v1.py pressure --map greenest_fields --zone GF_NE_PLATEAU
```

`fit(h, z) = ⟨u_h, m_z⟩` is the classical score — eco’s `netHorizonEV` rhyme for aces.

### L3 — Observe stamps (**shipped thin**)

Emitter: `tools/hero_observe_v1.py`  
Tape: `outbox/hero_observe_tape.jsonl` · face: `outbox/hero_observe.latest.json`

Wired:
- Drop settle → end of `attachments_v1.update_attachments_from_result` (co_deploy + outcome)
- Camp talk → `CampaignKernel.camp_talk` after successful `apply_pair_talk`

```bash
python tools/hero_observe_v1.py smoke
python tools/hero_observe_v1.py status
```

Schema sketch:

```json
{
  "schemaVersion": "verdance-hero-observe/0.1",
  "kind": "sortie_settle",
  "ran_on": "player",
  "heroes": ["vane", "ketha"],
  "mapId": "greenest_fields",
  "zoneId": "GF_NE_PLATEAU",
  "mapPressure": {"fog": 0.8, "sight": 0.5, "energy": -0.2},
  "events": [
    {"kind": "co_deploy", "delta": 4.0},
    {"kind": "outcome", "tags": ["success", "extract"]}
  ],
  "eta": 0.4,
  "umweltd_dark": false
}
```

Idempotent on recent `resultKey` / `talkId`. Best-effort — never blocks settle.  
Accumulate into counts / EMA later — **not** a live LLM planner.

### L4 — Tensor (aspiration, not now)

Want a sparse / low-rank object:

\[
\hat{y}(h, z, o) \approx \langle u_h, m_z \rangle + \sum_k A_{h k}\, B_{z k}\, C_{o k}
\]

or simply a dictionary of EMA updates on `(heroId, map_bucket, outcome_tag)`.

**Use later for:** soft deploy suggestions, support-bark eligibility, enemy disposition colouring, cognifold company face.  
**Never for:** god-brain merge, silent fake-live, replacing BeliefField/IntentResolver.

### Co-evolution rule (L1 ← L3)

Parametric web stays the prior. Play stamps **nudge** edge scores / promote complement gaps when η is honest:

- co-deploy success on high `fit` → strengthen couple  
- repeated avoid / wipe on high `fit` → lower η or flip motif to friction  
- degree cap remains; promotion is competitive (eco candidate sort energy)

Same law as cultivation: **don’t force Hearth↔Kiln; let evidence keep it.**

---

## 3b. Molecule policy brain (Stages 0–4 shipped thin)

Policy temperament SSOT + shadow stack + **opt-in soft blend**:

- Doc: `docs/MOLECULE_POLICY_BRAIN.md` · seal: `docs/MOLECULE_POLICY_SCORECARD.md` (vibe PASS)
- Stage 1 `D(u)`: molecule_doctrine (tool retired in pass 10; `va_molecule_doctrine.lua` is the kept output)
- Stage 2 φ: `data/story/phi_features.json` (phi_projector tool retired in pass 10)
- Stage 3 shadow resolver: shadow_intent (retired in pass 10)
- Stage 4: `va_molecule_policy=soft|shadow|off` (default **soft**; deployed to My Games)
- Faces: `outbox/molecule_doctrine_shadow.json` · `phi_shadow.latest.json` · `shadow_intent.latest.json`

Hand doctrine stays cache/override. Soft is character color, not a second brain.

---

## 4. Immediate next foundation steps (narrow)

1. ~~Define L2 mapPressure~~ → **done** (`map_umwelt.json`)
2. ~~Emit L3 observe stubs~~ → **done** (sortie settle + camp talk)
3. ~~Freeze molecule policy face + D(u) shadow~~ → **done**
4. ~~φ projector + shadow IntentResolver~~ → **done** (Stages 2–3)
5. ~~Soft live merge opt-in~~ → **done** (Stage 4; default off; vibe seal)
6. (Retired) the analyzer pass after molecule/web regen
7. **Play** — generate real tape rows; glance `hero_observe.latest.json`
8. **Next unlock:** Stage 5a Knock cadence when you want bond micro
9. **Do not** start full cognifold wishlist / L4 tensor until observe volume exists

Optional micro-polish (only if playtest complains):

- Diverge Rusk/Odessa molecules slightly  
- Soft-raise ledger marks or accept ledger as “quiet axis”  
- Allow isolate rescue pass for Commando/Consul when complement≥threshold
- Add more zone overlays as theaters open

---

## 5. Pointers

- Molecule policy brain (D(u) stages): `docs/MOLECULE_POLICY_BRAIN.md`
- Umwelt molecules: `docs/HERO_UMWELT.md`
- Support web: `docs/SUPPORT_WEB.md`
- Cognifold wishlist: `docs/UMWELT_GYM_PATHWAY.md`
- Quantum campaign / eco classical limit: `BAR_verdant_ashes_campaign/verdances_ashes_campaign_design.md`
- Disposition de-embed: `tools/quantum_bar_ai/campaign_manifold.py`
- Dual-gym law: `ws-win/yurt-sync/docs/UMWELT_PRIMARY_DUAL_GYM.md`

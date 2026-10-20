# Narrative Readings · Density Matrix as Narrative Compression

**Status:** v0.1 live (2026-10-19). DERIVE layer; never world truth.
**Law it lives under:** [`GRAPH_COLLAPSE_SSOT.md`](GRAPH_COLLAPSE_SSOT.md) — `process_result` is the only writer of G and H. Everything here is a projector over `state/campaign_state.json` and can be rebuilt from the save at any time.

---

## North star

The world graph G is a density matrix over **zones**: who holds what. That is the least narrative question the world can be asked. The narrative layer is a second density matrix, **ρ_N**, over **readings**: the handful of competing interpretations of what the company *is*.

| Part of ρ_N | Meaning | Comes from |
|---|---|---|
| **Diagonal** | how much the evidence supports each reading | *levels* — probes over current state |
| **Off-diagonal (coherence)** | two readings that no event has yet forced apart | *history* — event classes over beads |
| **Purity / entropy** | how far the campaign has decided what it is | derived |
| **Attractor** | the authored place in reading-space the company is nearest to | fidelity between the diagonal and authored signatures, filtered by coherence requirements |

Levels come from state. Coherence comes from history. That split is the design; keep it.

Dramatic ambiguity *is* coherence. A reveal *is* decoherence. Nobody picks "the sovereign route"; they keep doing things until Sovereign is the only reading left standing. Endings open when enough questions have been **forced**, not when a mission counter is reached.

---

## The objects

```
data/story/readings.json          8 readings, declarative evidence (probes), 6 coherence pairs
data/story/event_classes.json     29 event classes: detector, owner, occasion, witness, coherence effects
data/story/attractors.json        12 attractors: signature, requirements, leads, framing, edges
data/story/attractor_scenes.json  21 transition scenes with cast fallbacks
data/story/voices/<speaker>.json  7 leads + brakhov + pavise; blades.json (28); patrons.json (6)
tools/readings_v1.py              projector  -> outbox/readings.latest.json
tools/occasions_v1.py             selector   -> outbox/occasions.latest.json / .md (includes the roll)
tools/validate_story_v1.py        linter: every reference must resolve; projector determinism
tools/merge_ketha_additions.py    deepens the in-Drop pools in ketha_voice.json (idempotent)
```

### Readings (the basis)

`auxiliary` Hired Hands · `sovereign` Our Own Flag · `indebted` The Dealer's Ledger · `bleeding` Shorter Roster · `rooted` A Place to Stand · `armada_falling` The Old Flag Comes Down · `haunted` The Roll Is Longer Than the Roster · `hunted` Someone Is Looking for Us.

Each reading has `argues` (the voice that wants it true) and `resists` (the voice that wants it false). Characters with a reading to lose are characters the simulation can hurt.

### Probes (the only way a reading may touch state)

`rep`, `graph`, `tag_rate`, `verdict_rate`, `commitment`, `holdings_*`, `claimed_nodes`, `thread_*`, `flag`, `number`, `ledger_ops`, `tenebrium_low`, `wounded_named`, `dead_named`, `scars_total`, `home_level`, `walker_locked`, `front_flips`, `clashes_near_held`, `unobserved_held_maps`, `const`. Add a probe to `readings_v1.probe()` and the validator's `PROBES` before using it in data.

### Coherence pairs (the questions)

| Pair | Question |
|---|---|
| auxiliary \| sovereign | Whose war is this? |
| rooted \| bleeding | Is the camp a home or a hospital? |
| indebted \| sovereign | Who holds the paper? |
| haunted \| rooted | Do we go back for them? |
| hunted \| armada_falling | Is the pressure coming or going? |
| auxiliary \| indebted | Which creditor? |

`c` starts at 1.0. A distinguishing event multiplies `c` by `(1 − strength)` and records which reading it pointed toward; a renewing event moves `c` back toward 1. Status: **open** (> 0.66), **leaning**, **settled** (≤ 0.33 with a clear lean), or **torn** (forced both ways with comparable weight — the company has answered the question twice, differently). Snapshot classes that fire per hero apply their effect **once per class** with diminishing returns, so three carried frames do not outvote two dead ones by repetition.

### Event classes (the event surface)

An event class is *a thing the world does that a person in camp has the job of saying*. Firing one does three things: names a **witness** (the concrete noun for the writer), applies **coherence effects**, and gives the **owner** an **occasion** (`briefing`, `debrief`, `camp`, `roll`). Levels never come from event classes; coherence only ever comes from them. `cooldownBeads` is hysteresis: crossings speak once, then stay quiet.

Detectors run per **bead** (one `history[]` entry + its narrative event + its `frontEvents` + thread history at that turn + stamped `namedOutcomes`/`joined`) or on the **snapshot** (legacy saves, walker state, garrison scale).

### Attractors (the checkpoint graph)

Shelf → {Paid Work, The Hinge, The Infirmary, The Roll} → {Our Own Flag, The Ledger, Hearthfire, Ash Front} → three finale basins: **Their Flag, Our Hands** (overthrow), **Nobody's Paper** (sovereignty), **The Way Off** (spire). Finales require `settledPairsMin: 3`. Edges are authoring guidance and scene triggers, not gates; a trajectory may skip or revisit. Selection is Bhattacharyya fidelity on sharpened distributions with stickiness (`0.06`) so the company does not flicker between neighbours. A transition emits `attractor.transition.scene`, resolved against who is actually in camp via each scene's `fallback` chain.

### Voices (the generator contract)

The selector **never composes a sentence**. It picks an authored line for a `(speaker, event class, occasion, dominant reading, attractor)` tuple and fills the nouns from the witness fields. Preference: most specific line not said recently; `once` lines fire one time per campaign; Ketha is the universal fallback because she keeps the ledger. If nothing fits, the witness string is shown as narrator text, which is still a true sentence about the world.

| Tier | Who | Has |
|---|---|---|
| Voiced leads | Ketha, Vane, Rusk, Grath, Yeva, Hearth, the Last Auditor | register, owned classes, reading-conditioned lines, attractor openers, shift/settled/torn lines, death line |
| Seasoning | Brakhov | low-weight lines on everyone's classes |
| Anchor | Pavise | lines while alive; posthumous roll entry and Ketha's `heroId: pavise` lines |
| Blades | the other 28 | join / held / costly / death |
| Patrons | Anselm, Brask, Solvang, Voren, Ixt, Calder | dispatches keyed to classes, attractors and shifts; the enemy's unnamed roll |

**Owner table**

| Voice | Owns |
|---|---|
| Ketha | drop_unfinished, drop_lost, costly_return, hero_joined, named_dead, walker_*, bring_back promises |
| Vane | drop_held, own_ground, node_claimed, ground_came_to_us, contested crossing, shelter/company promises |
| Grath | merc_paper, scarcity crossings, loan_taken, friends promises |
| Rusk | frame_recovered (and the aside on every death) |
| Yeva | ground_changed_hands_near_us, clash_near_held, unobserved_ground |
| Hearth | clean_return, place promises |
| Auditor | own_ground_on_merc_paper, armada_flip_away, debt_cleared, garrison_scaled_up, dealer promises |

### The roll

Derived in `occasions.latest.json → roll`: the dead in the order they went, each with the owner's line, Rusk's aside, and the blade's last words; the carried, by name and count; the walker's state. `rollEntry` for Pavise is authored. The finale reads it back.

---

## Pass two: the belief world (Umwelt)

**Law:** Verdance is an Umwelt world. The company's comprehension is a belief field, not
a record. Truth lives in `state/campaign_state.json` (zoneMemory, frontEvents) and is not
shown to the player; **intel** is what reached camp. One engine under the house, the hive
and the war (`AQuantumArchitect/umwelt`; set `UMWELT_SRC=<umwelt>/src`, or keep a checkout at
`~/ws-win/umwelt`). Verdance stays importable without it: every belief step skips cleanly.

```
tools/umwelt_world_v1.py        DomainSpec from the zone graph + codex + the six questions; VerdanceWorld host
tools/umwelt_replay_v1.py       the gate: replay a save, check comprehension (5 checks)
tools/belief_homecoming_v1.py   fold a homecoming: fog grows, SURPRISE stamped, observe, intel split, save world
tools/camp_clock_v1.py          interstitial time: rest/wait/scout/post/recall, truth ticks, pauses
state/belief/verdance.engine.pkl   the company's mind (a legitimate second truth: about the company, never the world)
outbox/intel.latest.json        intel/1: every axis dark | stale | current, with age and provenance; the six questions as Bloch vectors
outbox/camp.latest.json         the clock, where everyone is, recent pauses
```

Spec: zones (`ours`/`held` unitary; `strength`/`threat` dissipative, bridged along adjacency), people
(`fit`/`pressure`/`frame_intact`), the company (six questions as icon-axes, dissipative and slow so an
unforced question reopens), one driver: the Verdance day. Passed Umwelt's `spec.validate` gate
(resolve, schema, topology, bindings-strict, boot-blank, synthetic exercise, save/load).

η: Drop telemetry 1.0 · posted hero 0.7 · scout patrol 0.55 · adjacent inference 0.2 · rumour from a held
map 0.25–0.35, elsewhere 0.1–0.15 · question pushes = the event class's strength. Boot is primed to
"nobody has looked" (four 0.5 observations), so a value nobody measured renders **dark**, never zero.

**Surprise** is stamped on every bead by the fold, before looking: Σ over measured zones of belief
confidence × |truth − belief|. Zero on a first visit. The `surprise_at_drop` event class (Yeva) fires
at ≥ 0.6 with the top zone's "believed / found".

**The questions as Bloch vectors:** z is the lean, the radius is how committed, and *torn* is a short
vector after being pushed both ways (tallied per question). `umwelt_replay_v1` checks the Umwelt
estimator never leans opposite to the readings face on the same evidence.

**The camp clock** (`/api/camp`, `/api/camp-act`): time runs in hourly steps; truth evolves only through
the engine's own `tick_offscreen_zones` / `run_offscreen_clashes`; the belief world eases; posted people
measure their ground every hour (looking is keeping); rumours that reach a held map enter `state["intel"]`
with provenance. Time stops at the first **pause**: contact (a posted hero's ground changed hands), rumour,
a question changing status, an arrival, or the action's end. Pauses are minor beads on `state.camp.pauses`.
A hero stands up from the wounded bench after 12 h of rest. People have places: camp / transit (with an
ETA) / posted / field (a frame, where it fell).

Gate on your archived mission-5 save: 36/36 measured axes track truth, 90/90 unmeasured dark, a rumour
fades over three silent days, six questions consistent with the face, save/load hash-stable.

Known gaps: `world_zone_graph.v1.json` lacks 6 zones that exist in zoneMemory (handled as unbridged nodes;
regenerate the graph); the hub still renders `war_map.json` (truth) and should switch to `intel.latest.json`
(pass three); no casualties on scout/post yet; a Drop with posted heroes should exclude them from the roster.

## Pass two, closing: readings read belief; story objects take the S3 shape

**Readings about the world read what the company knows.** Probes `belief_holdings_count`,
`belief_holdings_ratio`, `belief_dark_share`, `belief_threat_near_held` read `outbox/intel.latest.json`;
`intel_count` reads `state.intel` (what reached camp); `question` reads the Umwelt Bloch vectors so the
company's own sense of a question feeds the levels at moderate weight. Readings about the company itself
(roster, promises, debt, the roll) still read state. Every belief probe falls back to truth on a fresh
campaign and says so in its witness (`source: truth-fallback`). The four offscreen event classes
(`armada_flip_away`, `ground_came_to_us`, `ground_changed_hands_near_us`, `clash_near_held`) detect from
intel rows with `fallbackFront` for legacy saves. Consequence: the cast now speaks to rumours, not to truth.

**The dance tape** (`tools/story_dance_v1.py`, `state.dance`): story objects evolve by the strand-dance verbs
from S3 — ✨ creation (a thread opens, a hero joins, an attractor entered first) · → push (a Drop advances the
strand; a thread is committed; a frame carried home) · Δ fission (a commitment splits a thread into an
obligation with a deadline) · ∇ fusion (the roll grows) · T transform (dominant reading moves, a question
changes status, an attractor transition) · ∅ null (a promise lapses, a death: **the obligation survives** —
"recover the frame of Pavise on greenest_fields; read Pavise on the roll"). Append-only, content-addressed,
parent-linked; `once` keys make a repeated attempt the empty dance.

**Truth / goodness / beauty per bead** (`bead.tgb`, never one score): truth = what happened (verdict,
extraction, zones measured, surprise, dead, carried); goodness = what was promised (kept, lapsed, still open);
beauty = how it reads (attractor, dominant reading, transition, scene, the opener line).

**The chronicle** (`tools/chronicle_v1.py` → `outbox/chronicle.latest.json/.md`): the φ record folded the
brain-ant way. Consecutive Drops under one attractor fold into a chapter row with n, missions, verdicts,
dead, carried, surprise; named events never fold; "Still owed" lists every ∅/Δ whose obligation no later
push has answered. Referee: fewer rows than events, every kept icon survives, `last_done` queryable.

Icons are now on every reading, coherence pair, event class and attractor; the validator warns on a
missing one. One glyph vocabulary across the hub chips, the briefing, the roll and the chronicle.

## Pass three: into and out of BAR — truth, belief, and the other minds

**One shape for every perspective.** Truth is projected into the same `verdance-intel/1` node shape as
belief (`outbox/truth.latest.json`, confidence 1, `perspective: truth`, **hidden**; `/api/truth` is dev-only).
Every belief is a lossy reading of that one truth, and every mind is DERIVE: none writes world state.

**Perspectives** (`tools/perspectives_v1.py`). Besides the company's mind
(`state/belief/verdance.engine.pkl`) there is one Umwelt world per faction
(`state/belief/{armada,nullmercs,cortex}.engine.pkl`), fed by an **observation policy** instead of a player:
zones they control η 0.9 · adjacent η 0.4 · clashes touching their ground η 0.8 · flips from/to them η 1.0 ·
a Drop fought on their ground η 0.8 (they learn the irregulars were there). The roles are per-mind — Armada's
`ours` means Armada's — so perspectives are compared only through truth. Faces: `outbox/intel.<faction>.latest.json`.

**Divergence** (`outbox/divergence.latest.json`, `/api/divergence`) is the surprise map stated as objects:
per perspective, belief vs truth — `right`, `ghostHoldings` (believes it holds what it lost), `unknownHoldings`
(holds what it does not believe it holds), `wrongHeld`, `dark`, `gap` (Σ conf·|truth−belief|); and
**crossed**: what each faction knows of the company's ground (`known` / `suspected` / `blind`).
The patrons speak from it: a dispatch may carry `{"on": {"belief": {"blindGte": n | "ghostGte": n | "knowsAll": true}}}`
and is written from what its author's faction **believes**, never from truth ("Command's map shows two
sectors more than the ground does"). Fields `armadaKnows / armadaBlind / armadaGhost / armadaOfOurs` (and
per faction) are common occasion fields. At most two dispatches a bead, never two from one desk.

**Out of BAR — the result contract** (`contract_v2.normalize_result` carries both through):
- `observedZones {zoneId: η}` — line-of-sight share per zone, recency weighted (the gadget, pass 4). Until
  it exists the fold uses a **footprint proxy**: deploy/extract/target/footprint/objective/claim zones 1.0,
  their neighbours 0.5, the rest of the fought map 0.15 (minimap awareness); legacy results 0.6.
  The bead stamps `observedZones`; the Drop's telemetry is observed at exactly that η per zone.
- `beliefExport {zoneId: {ours, held, strength, threat}}` — what the HUD believed at exit, ingested at its own η.
- **Surprise is η-weighted**: `Σ η·conf·|truth−belief|`; `bead.surprise.top[].eta` says how hard we looked.
  (A ghost holding seen at 0.15 is a rumour; at 1.0 it is Yeva's line.)

**Into BAR — the sortie stamp.** `intent.intel` (`verdance-intent-intel/0.1`, perspective **company**):
for the planned map, every zone's `ours/held/strength/threat` as `{value, confidence, state, age_min, source}`
— belief, not truth; the six questions; who is `posted`/in `transit` and where; which `frames` lie where
(open ∅ obligations). Pass 4 draws belief on the HUD until line of sight confirms or surprises it live.

**Cost law.** Each mind is a full Umwelt world and Umwelt's save/load walks the continuation surface, so the
three faction minds cost ~10× the company's fold. They are **off the critical path**: homecoming and every
camp action `enqueue()` a job (a frozen truth slice + fronts + the fought map) and spawn a detached,
low-priority, single-thread worker (`perspectives_v1.py --worker <ws>`); jobs queued back to back coalesce;
divergence is rewritten when the worker lands. `/api/divergence.pending` says `{queued, workerAlive}`.
Truth and the company's own fold stay synchronous. `VA_PERSPECTIVES_SYNC=1` folds inline (tests);
`VA_PERSPECTIVES_NOSPAWN=1` queues without spawning (gates).

**Routes.** `/api/intel?perspective=company|armada|nullmercs|cortex` · `/api/truth` (hidden) ·
`/api/divergence` (hidden) · `/api/chronicle` · `/api/camp`, `/api/camp-act` (pass two).

**Gate.** `tools/umwelt_replay_v1.py` still passes 5/5 on a pass-three save (measured track truth 36/36,
unmeasured dark 90/90, rumour fades, questions agree with face 6/6, save/load hash).

**Pass 4 (BAR / LuaUI) inherits:** export `observedZones` and `beliefExport` from the gadget; draw
`intent.intel` as the pre-LOS overlay; posted heroes out of the Drop roster; casualties on scout/post;
regenerate `world_zone_graph` for the 6 unbridged zones; vendor the Umwelt snapshot in SHIP.bat.

## Pass four: BAR / LuaUI — the belief goes in, the looking comes out

**Out: `game_verdance_belief_observe.lua`** (synced, its own chunk — the campaign gadget sits at the
Lua local limit). Every 2 s it samples up to 36 cell centres per zone against the player's line of
sight: `eta = max(eta·decay, share)` with an eight-minute half-life, so a zone driven through reads
≈1.0 at exit and a zone glanced at an hour ago has faded to a rumour. It also counts what stood in
the seen cells by side (units, structures, peaks, "enemy seen recently"). Published as
`GG.VA_ObservedZonesJson()` / `GG.VA_BeliefExportJson()`, spliced into `resultJson()` as
`observedZones` / `beliefExport` (two lines, no new locals), and live as GameRulesParams
`va_obs_<zone>`, `va_obs_enemy_<zone>`, `va_obs_tick`. The Python fold observes the Drop's truth
at exactly that η per zone; the footprint proxy is now only the legacy fallback.

**In: `generated/va_intel_current.lua`** (`tools/intel_lua_v1.py`, written whenever the intent is
materialised, mirrored into the customer pack with `va_current.lua`): `intent.intel` as a Lua
table — per zone `ours/held/strength/threat = {v, c, state, age, src}`, the questions, posted people,
open frames. Belief, not truth; a fresh campaign ships an empty table (nobody has looked).

**The overlay: `gui_verdance_belief_overlay.lua`.** Minimap tint per zone by what we believed
(ours / held by someone / empty / "?" where nobody looked), alpha by confidence, fading to nothing
by η 0.6 — line of sight replaces belief and the real map shows through. When a well-seen zone
contradicts the briefing (believed ours, found a column; believed theirs, found empty; a blank
with a column in it) Yeva says so once (`VA_SURPRISE_LIVE` in the log), and the same contradiction
comes home on the result as surprise. `/vabelief` toggles the tint, `/vabeliefpanel` a per-zone
table (belief → seen), `/vabeliefrebuild` reloads the files.

**Bodies are where they are.** `roster.heroes` on the intent excludes anyone the camp clock has
posted or in transit (`roster.awayFromCamp` lists them); recall first. Looking costs: a posted
hero on hostile ground risks a wound every hour (`0.015/h`, plus `0.010·instability`), comes home
in transit, and the pause is a `casualty` (🩸 on the dance tape); a patrol into hostile ground has a
one-in-five chance of not all coming back — a cadre unit is spent and its report lands at η 0.35
instead of 0.55. All rolls are hashes of who/where/when, so a replay lands the same wounds. Only
company members take a post; the wounded rest first.

**The hub.** `app/showoff/console/camp.js` mounts into the console's **Home** workspace: the clock,
known/stale/dark, run-the-clock actions (rest, wait, scout, post, recall → `POST /api/camp-act`),
who is away, what the clock said, last homecoming's surprise, the six questions, the belief table
per map (from `/api/intel`, never truth), and what Armada knows of us (from `/api/divergence`,
with "still catching up" while the worker runs). The folded record (`/api/chronicle`) renders under
**Chronicle**. Legacy tab layout gets a fourth "Camp" tab instead.

**Ship.** `scripts/ship.ps1` stages the pass one–four tools and vendors a snapshot of Umwelt's
`src/umwelt` package into `tools/_vendor` (from `UMWELT_SRC`, a sibling clone, or `~/ws-win`);
`umwelt_world_v1._umwelt()` tries that path last, after a live clone. `requirements-ship.txt`
gains numpy. FREEZE law stands: the snapshot is distribution, not a fork — nothing in it is edited.

**Checks.** `tools/luachk_v1.py` is a structural Lua check (no interpreter on the build hosts):
brackets and block balance; all 40 mod files pass. The 6 "unbridged" zones were legacy ids in an
old save; a fresh campaign's 102 zones all sit on the graph, so no graph regeneration was needed.

**Open after pass four.** The gadget's belief export is coarse (sides and counts, not control
inference); posted heroes do not yet appear as units in a Drop on their own zone; the hub does not
yet draw belief on the theater board itself (the table is the first form); `va_obs_*` is not yet
read by the objectives widget for "unconfirmed" markers.

## Pass five: the boundary — in quiet, out by manifest

**Principle.** Lua reports facts; Python interprets. The Drop is a window onto one zone-cluster of the
world graph for a while. Nothing inside it needs a verdict, a timer, or a mechanic the graph does not
already have. The gadget knows nothing about victory.

**One pad.** The company lands and lifts from the same ground, like raiders: `extractionZoneId ==
deploymentZoneId` (engine), the deploy beacon, the bought kit and the exfil pad all read the zone anchor
(`generated/va_pad_current.lua`, written with the intent). A manifest destination that is a zone makes
the next sortie on that map land there (`camp.nextPadZoneId`); traversal is a travel sortie, not a
different pad.

**The way out.** `EXTRACT` (objectives widget) → `VA_CMD:manifest` → `game_verdance_exfil.lua` counts
the pad (radius 560): heroes and units on it are **going**; heroes, units and structures off it are
**staying**, by zone; `enemyOnPad`; `seen` = η per zone from the observe gadget; destinations = camp +
same-map holdings of ours + the graph's map links out. `gui_verdance_exfil.lua` pauses the game and shows
it with the **company's** belief beside what was looked at (the other minds are never shown). Enter →
`VA_CMD:extract:<dest>` → the manifest is stamped on the one result (`result.manifest`) and the
campaign gadget ends the sortie: no hold timer, no zone-ownership gate, no soft clock, no stalemate,
no Mode A continue, no debug terminals, no receipts, no live commands, no two-frame "UPDATING THE WAR".
Esc → back to the field. Nobody left → `GG.VA_WipedManifest()` stamps an empty one. The engine ending
the game without a manifest → `closed`.

**Python reads the manifest** (`tools/manifest_v1.py`): verdict — wiped → defeat, closed → abandon,
extracted → victory if the objective was done and nobody was left, else partial; `extractionStatus`
contested when enemies stood on the pad; people left stand where they stood (`camp.people[hid] =
{where: "field", zoneId}`), do not board the next Drop until recalled, and the dance tape owes "bring
<name> back from <zone>"; structures left are the footprint and the zone's holding — a holding is a
holding whoever's it is.

**They respond to what they see.** The observe gadget runs symmetrically: `va_seen_<zone>` is the
recency-faded share of our units some enemy ally team has in line of sight (weighted by how many).
`enemyResponseTarget()` sends QRF, escalation, beat and hot-extraction packs to the zone the enemy
*believes* we are in, falling back to the pad, never to our true centroid. No heat meter, no comms.

**The bridge, kernel-owned** (`tools/verdance_kernel/sortie.py`): Drop = gate → stamp → intent →
`sync_mod -Copy` (the workspace mod is copied into `data\games` every Drop; the workspace is the
truth) → **one** build (installer writes the seed and startscript) → the kernel starts `spring.exe
--write-dir <barDataRoot> --only-local <startscript>` itself and remembers the spring pid and the infolog
size. One watcher tails the infolog from there every 2 s, reassembles each `VA_RESULT_JSON_BEGIN..END`
block in Python (chunk `i/n` checked; COMPACT retired), writes `inbox/archive/<resultKey>.json` +
`latest_va_result.json`, and calls `bring_home` once per unprocessed key. Spring exits with no key →
`incomplete`; a duplicate key still counts as home. `/api/session` reports the watch
(`launching → in-game → bringing-home → home | closed-without-result`). Retired: `play_session_v1`,
`run_full_cycle_v1`, `extract_latest_result.ps1` on the player path (operator/headless tools keep them),
`_sync_customer_seed`, `/api/field`, `/api/continue`, `/api/extract-leave`, the receipts file, the live
command file, the field packet, `next_sortie_choice.json` from Lua, the second build, `abandon` while
Spring runs.

**Numbers.** campaign gadget 9,216 → ~7,870 lines; objectives widget 3,728 → 2,549; new: exfil gadget
~330, exfil widget ~330, sortie.py ~330, manifest_v1 ~100. Result verdict strings in Lua: 12 → 3 kinds.

**Open.** The builder still composes a player kit the gadget discards (one `crew[]` from Python is the
next cut); the seed is still produced by PowerShell; a hero left in the field is not yet spawned as a unit
on return; the hub debrief does not yet draw the manifest.

## Pipeline

```
BAR Drop → MatchResult → bring_home → process_result
   ├─ bead stamped with joined[] and namedOutcomes[]          (patch 1)
   ├─ belief_homecoming_v1.fold_homecoming → bead.surprise, state.intel, state/belief/, intel.latest.json
   ├─ readings_v1.project  → outbox/readings.latest.json      (patch 2; reads belief/intel for world facts)
   ├─ occasions_v1.build   → outbox/occasions.latest.json/.md (patch 2)
   ├─ story_dance_v1.fold_homecoming → state.dance, bead.tgb; chronicle_v1.write → chronicle.latest.*
   └─ materialize_next_intent → generate_briefing
         reads occasions.latest.json for this mission          (patch 3)
         cast lines replace the level-triggered pressure/war lines
```

Hub consumers: `occasions.latest.json` → `briefing[]`, `debrief[]`, `camp[]`, `roll`, `dispatches[]`, `blades[]`, `transition` (scene id to stage). `readings.latest.json` → chips for the diagonal, the open questions, purity, attractor framing.

In-Drop voice (HUD barks, pre-seeded debrief candidates) still comes from `ketha_voice.json` pools, hash-seeded per mission; the pools that fire most were deepened to 6–7 lines. Between-Drop voice is the readings layer.

---

## Vocabulary

Banned in any character's mouth: measurement, collapse, axis, density, estimate, band, confidence, coherence, uncertain, superposition, qubit.

| System | Mouth |
|---|---|
| unresolved zone | "nobody's looked" |
| measured | "we were there" |
| collapse | "what we found instead" |
| decoherence | "what happened while we weren't watching" |
| estimate band | "a picket, maybe a battalion" |
| coherence open | "nobody has asked yet which it was" |
| torn | "we answered that both ways" |

The hub chips may keep short system labels. The characters may not.

---

## Extending

- **Add a reading:** append to `readings.json` with evidence from existing probes; add it to at least one coherence pair or it can never be forced; give it `argues`/`resists`; add signature weights in attractors you want it to pull toward.
- **Add an event class:** detector (bead or snapshot), owner, occasion, witness with fields the detector produces, coherence effects on listed pairs, cooldown. Then give the owner 3–6 lines and Ketha one fallback.
- **Add an attractor:** signature over readings, requirements, leads, framing, edges with scenes; write `enter:<id>` with a fallback pair.
- **Add a voice line:** `on` keys are `class`, `thread`, `heroId`, `attractor`, `dominantBecame`, `coherenceSettled{pair,toward}`, `coherenceTorn{pair}`; `reading.dominant` filters; `occasion`; `once`; `weight`.
- **Always:** `python tools/validate_story_v1.py` (0 errors), then `python tools/readings_v1.py` and `python tools/occasions_v1.py` on the live save and read the markdown like a player would.

---

## Engine patch (2026-10-19)

Three additive edits to `tools/verdance_story_engine_v1.py`, each guarded so homecoming can never fail because of them. Pre-patch copy: `_attic/verdance_story_engine_v1.pre_readings_2026-10-19.py`. Test suite failure set identical before and after (45 pre-existing; most are `datetime.UTC` on Python < 3.11).

1. `process_result`: `bead["joined"]`, `bead["namedOutcomes"]` — closes the roll data gap.
2. `process_result`: derive both faces once per homecoming, carrying forward once-lines and recency.
3. `generate_briefing`: `_occasions_briefing_lines()`; when present, drops the `war`/`warband` pool lines and skips the level-triggered pressure block.

---

## Data gaps and next steps

- **The surprise at Drop start.** Yeva's best material is `measured − briefed`. `process_result` should stamp the pre-Drop `expectedPresenceBand` and the observed presence for the deployment zone into the bead; then an event class `surprise_at_drop` with witness "we briefed a picket; there was a battalion".
- **Knowledge decay and rumor.** Per-zone `confidence` should widen with time since measured and narrow with adjacency to a measured zone; offscreen clashes seen from an adjacent measured zone become rumors with a source. This is the player-facing form of decoherence and it is all classical bookkeeping.
- **Pressure on heroes.** A derived per-hero scalar from a small want-graph (home zone, grudge, bond, reading they argue) to gate camp talks instead of the rank-C/B/A ladder.
- **Retire `camp_talks.json` stubs.** 263 of 488 hero lines are the hero's own hook verbatim; four template lines recur across pairs. Keep the 28 authored talks, the 32 scenes and the leadership reactions as the bar; use the chemistry model only as a pair selector.
- **Hub UI.** Stage `transition.scene` and the roll; show the open questions as questions.
- **Lua port.** `occasions.latest.json` is already the contract the RmlUi hub needs; the projector itself can stay in Python until the Lua snapshot is authoritative.
- **Roster thinning (recommended, not done):** halbard, bro, twitch, consul, kit, stride → unnamed.

---

## The portfolio claim, stated plainly

Unstructured events (beads, offscreen clashes, promises kept and broken, deaths) → a small vocabulary of probes → a weighted mixture over competing **readings** with explicit, computable **ambiguity** between them → authored **attractors** chosen by fidelity → content keyed to the interpretation, never to the raw signal. The pipeline is rebuildable from the log, deterministic, and linted. Replace "Drops" with support tickets or field reports and nothing in the architecture changes; only the readings and the voices do.

## Pass six: the board rhymes with the field (2026-10-20)

The HUD paints the **company belief** — never the truth, never the enemy minds — the same way in the hub and in BAR, with colour, shape and border each carrying the same fact.

**Belief on the board** — `tools/hub_belief_v1.py` reads `outbox/intel.latest.json` (the pass-three frame) into one row per zone: `believed ours|held|empty|dark|unsure`, `confidence` (alpha), `state current|stale|dark` (ring), `faction` = who we last **saw** holding it (`umwelt_world_v1.seen_faction`, kept in `.seen.json`; rumours flip it, nothing else does), `threat`, `surprise`, `people[]`, `holding`. `build_hub_state_v1` no longer reads `zoneMemory.controllingFaction` for colour; theater `control` comes from belief. A faction colour on the board means "we believe they hold it", at that confidence. Hub keys: `belief`, `camp`, `exposure` (our side of the mirror only: which of our holdings Armada has eyes on), `lastResult.manifest`.

**One pad, constrained choice** — raiders land and lift at the same point. The hub shows one Pad mark; `stamp_deploy_plan_v1` sets `extract = deploy` and judges legality from belief: ours, or a rim believed empty/dark/unsure with threat ≤ 0.4, or `camp.nextPadZoneId`. Illegal zones are rendered with a struck ring and refuse the click; the reason is the belief sentence ("believed held by armada (88%)"). Heroes left in the field (`camp.people[hid].where = field`) are not deployable and show where they are.

**In BAR** — `gui_verdance_objectives.lua`: pad ring (r = 560, `Ash.MARK.pad`) with a live headcount chip; EXTRACT is three-state (empty pad / someone off the pad: "LEFT IF YOU LIFT" ledger / all aboard); SEEN row and exposure hatch from `va_pad_enemy` and the observe gadget; contradiction glyphs where the briefing was wrong; phase chips ▸ APPROACH ✦ FIGHT ◆ MARKS ⌂ EXTRACT ∞ OVERTIME (the clock never ends a sortie, overtime only wakes the map). `gui_verdance_tnb_bar.lua` is the first-class Tenebrium bar top-centre (bank · looted · field, pips, rise/fall flash) fed by `publishTenebriumRules()`; the broken donuts are gone. `gui_verdance_exfil.lua` is reskinned on the Ash tokens and fences input with `WG.vaExfilModal`.

**Cut** — the old `controllingFaction` colouring, Tnb donuts, verdict tables in `va_ash_tokens.lua`, hold-timer copy (`narrative_v1.bringHome` now describes the manifest). Pre-sweep copies in `_attic/sweep_tmp/`.

**Still open** — the builder composes a player kit the gadget discards (next cut: `crew[]` from Python); heroes left in the field are not yet spawned as units on return; nested zone geometry overlaps on the Greenest Fields board.


---

## Commands

```
python tools/validate_story_v1.py        # lint content, check projector determinism
python tools/readings_v1.py              # readout + outbox/readings.latest.json
python tools/readings_v1.py --fresh      # ignore previous face (no stickiness/transition)
python tools/occasions_v1.py             # who says what; writes occasions.latest.json/.md
python tools/merge_ketha_additions.py    # idempotent pool deepening
python tools/umwelt_replay_v1.py         # belief gate: replay the save, 5 checks
python tools/perspectives_v1.py          # fold the faction minds once, print divergence
python tools/perspectives_v1.py --worker . # drain the perspectives job queue
python tools/camp_clock_v1.py            # camp surface
python tools/intel_lua_v1.py             # rewrite generated/va_intel_current.lua from the intent
python tools/luachk_v1.py <files.lua>    # structural Lua check
```

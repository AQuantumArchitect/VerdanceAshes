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

## Pipeline

```
BAR Drop → MatchResult → bring_home → process_result
   ├─ bead stamped with joined[] and namedOutcomes[]          (patch 1)
   ├─ readings_v1.project  → outbox/readings.latest.json      (patch 2)
   ├─ occasions_v1.build   → outbox/occasions.latest.json/.md (patch 2)
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

---

## Commands

```
python tools/validate_story_v1.py        # lint content, check projector determinism
python tools/readings_v1.py              # readout + outbox/readings.latest.json
python tools/readings_v1.py --fresh      # ignore previous face (no stickiness/transition)
python tools/occasions_v1.py             # who says what; writes occasions.latest.json/.md
python tools/merge_ketha_additions.py    # idempotent pool deepening
```

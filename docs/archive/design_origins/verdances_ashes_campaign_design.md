# Verdance's Ashes — Campaign Design Document
### *Beyond All Reason · Ashwalkers Demo Campaign · Draft 0.2*
### *Quantum Graph Edition — revised from eco manifold inspiration*

**Primary sources:**
- Verdance's Ashes (planet): https://www.beyondallreason.info/universe/verdances-ashes
- Armada background: https://www.beyondallreason.info/lore/armada-background
- Cortex background: https://www.beyondallreason.info/lore/cortex-background
- Known Space: https://www.beyondallreason.info/lore/known-space
- Economy guide: https://www.beyondallreason.info/guide/in-depth-look-at-economy
- Classical eco manifold (inspiration): https://bar-eco-manifold-five.vercel.app/
- BAR GitHub lore repo: https://github.com/beyond-all-reason/lore

---

## 0. The Central Idea

The classical BAR eco manifold asks:
> "Given my current state (BP, M/s, E/s, storage), what action maximizes value over a planning horizon?"

The quantum campaign graph asks:
> "Given the current world-state (faction pressures, biome conditions, history, entangled
>  allegiances), what actions are *available*, what do they *cost*, and how do they
>  collapse the future?"

The difference is not cosmetic. In the classical manifold, map conditions are fixed parameters
you slide. In the quantum graph, map conditions are **entangled with faction state** — a
Cortex-held Scaffold Ruins has different effective energy income than an Ashwalker-held one,
because the Taelith grid degradation rate depends on who is maintaining the atmospheric
processors. You cannot decouple the economy from the politics. The density matrix holds both.

The eco manifold is the classical limit of the quantum graph — what you get when you
partial-trace out all the faction/lore axes and keep only the scalar economy. It is still
useful (the `netHorizonEV` scoring concept translates directly), but it is not the full picture.

---

## 1. Core Concept

A single-planet open-ended campaign set on **Verdance's Ashes**, a former Armada Horizon
world in active collapse. The player commands a **Void-touched Commander** operating outside
faction authority, leading a coalition called the **Ashwalkers** — drawn from Null-Mercs,
Independent clan fighters, and defectors from both factions.

**Two simultaneous functions:**
- A *narrative tour* through the lore of Beyond All Reason, teaching the player the world
  through play
- A *proof-of-concept* for procedurally generated missions driven by a quantum graph
  world-state, where the AI opponents, economy conditions, and available actions all
  de-embed from the same graph structure

---

## 2. The Planet: Verdance's Ashes

**Status:** Contested Line World — nominal Armada (House Taelith), rapidly destabilizing
**Faction assignment Q0:** `|Ψ⟩ = 0.77|ARM⟩ + 0.23|COR⟩` at mission start; drifts with play
**Schism Q1:** Taelith-dominant (Biogenesis + swarm + terraforming flavour)
**Void axis Q2:** Low — physical, earthly, no deep space anomalies
**Process-time Q5:** φ = OT-3970 (Ashen Accord era, active decay)
**Contested Q6:** 0.85 — near maximum superposition
**Tenebrium Q7:** 0.02 — depleted; no strategic reserves on-planet

### Biome Zones (P2 sub-axis — terrain diversity)

Verdance's Ashes is *partially terraformed*, which drives its visual richness. Each zone
is a different stage of Taelith engineering success, abandonment, or reversion. Critically,
**each zone has its own biome modifier vector** that reshapes the effective economy:

| Zone | Terrain | `spotMult` | `windMult` | `eBuildPenalty` | `bpMult` | Campaign flavour |
|------|---------|-----------|-----------|-----------------|---------|-----------------|
| Verdant Canopy | Megaflora jungle | 0.9 | 0.7 | 0 | 0.95 | Protect/escort; bots favoured; clan territory |
| Ashfields | Volcanic flats, original surface | 1.0 | 1.0 | 0 | 1.0 | Reclaim/hold; oldest settlements; reference zone |
| Scaffold Ruins | Abandoned Taelith infrastructure | 1.4 | 0.6 | 15 E/s | 0.85 | Capture/sabotage; contested chokepoints; Taelith grid degrading |
| Surge Flats | Low-gravity floodplains, periodic flood | 1.1 | 1.2 | 0 | 1.0 | Expand/race; hovercraft viable; flood timer urgency |
| The Scar | Orbital strike crater, irradiated edge | 1.8 | 0.5 | 8 E/s | 0.75 | Assault/survive; highest metal reclaim; wreckage from multiple eras |

**Reading the table:** `spotMult` scales effective metal spot value (reclaim abundance).
`windMult` scales wind income (atmospheric processor integrity). `eBuildPenalty` is a
constant energy drain (Taelith grid failure or irradiation). `bpMult` scales effective
build power (harassment level, terrain difficulty).

These biome modifiers are the **seam between the quantum graph and the classical eco math**.
When a mission is generated, the zone's modifier vector is applied to the player's base
economy state before any build decisions are evaluated. The "what should I build here?"
question is answered by the classical manifold logic — but *which* classical manifold the
player is on depends on the quantum graph's current zone control state.

---

## 3. The Quantum Graph — Formal Specification

### State Space

The world-state of Verdance's Ashes at any moment is a density matrix ρ over 8 qubits:

```
Q0  [Armada ↔ Cortex]         — top-level faction axis; Ω
Q1  [Scholarborne ↔ Evermarch / Concordat ↔ Divinitas]  — internal schism; α
Q2  [Void ↔ Structure]        — deep space / codified order
Q3  [Biogenesis ↔ Cold Divergence]  — change vs preservation
Q4  [AI Synthesis ↔ Human Sovereignty]  — machine role axis
Q5  [φ — process-time]        — causal timeline epoch
Q6  [Line World contested ↔ Terminal Verge]  — zone control
Q7  [Tenebrium abundant ↔ scarce]  — resource / economic pressure
```

**Sub-cluster P** hangs beneath each active zone node and carries the biome modifiers:
`{ spotMult, windMult, eBuildPenalty, bpMult, atmosphere, thermalBand, stability }`.
P-axes are only resolved when a zone becomes an active mission theater. This is the
**sparseness property** — most of the graph is unspecified until measured.

### Initial Conditions (OT-3970, campaign start)

```
ρ₀(Verdance's Ashes):

Q0:  |Ψ⟩ = 0.77|ARM⟩ + 0.23|COR⟩
Q1:  |Ψ⟩ ≈ 0.90|Taelith⟩               (Taelith dominant, some Evermarch seeping in)
Q2:  |Ψ⟩ = 0.15|Void⟩ + 0.85|Struct⟩
Q5:  φ = OT-3970.0
Q6:  |Ψ⟩ = 0.48|ARM⟩ + 0.28|COR⟩ + 0.24|IND⟩   (maximum superposition)
Q7:  |Ψ⟩ ≈ 0.98|scarce⟩

Faction pressure scalars (drive mission frequency):
  Armada:              0.62
  Cortex:              0.21
  Independent clans:   0.74
  Null-Merc density:   0.43
```

### State Evolution

```
ρ(t+1) = U(outcome) · ρ(t) · U†(outcome)

U(outcome) is determined by:
  - Mission result (win / loss / partial)
  - Path actions taken (A/B/C allegiance moves)
  - Economy state at mission end (μ, ε, BP ratios — see Section 5)
  - PvP meta-campaign contributions (multiplayer input to global ρ)

The manifold is unitary between measurements.
A "measurement" is a completed mission — the world collapses locally.
Between missions the next mission's content is genuinely uncertain.
```

---

## 4. Economy as World-State Variables

The classical eco manifold tracks scalars. The quantum campaign promotes those same scalars
into the graph as **observable fields** — they are still computed classically per-tick, but
their *thresholds* trigger quantum state transitions.

### Primary Economic Variables

| Variable | Symbol | Graph role | Classical analogue |
|----------|--------|-----------|-------------------|
| Metal income (M/s) | μ | Q7 sub-axis: resource throughput | `metalIncome` in state |
| Energy income (E/s) | ε | P3 sub-axis: stability capacity | `energyIncome` in state |
| Build Power | β | Q6 sub-axis: faction expansion rate | `buildPower` in state |
| Military Power | MP | Q6 direct: combat threat level | aggregate army value |
| Defense Power | DP | Q6 direct: zone hold capacity | fortification density |
| Net Horizon EV | η | mission-level score | `netHorizonEV` from manifold |

### Biome-Modified Economy State

The effective state fed to any build evaluation is:

```
effectiveState = {
  metalIncome:   baseMetalIncome  × zone.spotMult,
  energyIncome:  baseEnergyIncome × zone.windMult  -  zone.eBuildPenalty,
  buildPower:    baseBuildPower   × zone.bpMult,
  metalStored:   metalStored,
  energyStored:  energyStored,
  metalStorage:  metalStorage,
  energyStorage: energyStorage,
}
```

This is the bridge: the zone's quantum-graph-derived modifier vector is applied before
classical manifold scoring runs. The classical payback curves, ROI surfaces, and waterfall
simulations are all valid — they just operate on the *effective* state, not the base state.

### Eco Thresholds → Graph Transitions

```
μ (Metal income) thresholds:
  < 10 M/s   → Ashwalkers desperate; emergency no-build missions unlock
  10–30 M/s  → Normal operational tempo
  > 50 M/s   → Taelith notices; triggers Commander-level Armada response
               (Q0 shifts +0.08 toward ARM eigenstate)

ε (Energy income) thresholds:
  < 5 E/s    → Atmospheric processors failing; P0 atmosphere degrades;
               disease debuff activates (unit HP penalty)
  > 100 E/s  → Jump Spire charging eligible (Path C prerequisite)
  > 500 E/s  → Void resonance possible; Q2 shifts +0.05 toward Void

β / DP ratio:
  β >> DP    → Player is aggressive; Cortex probes rear (Q0 shifts +0.03 COR)
  DP >> β    → Player turtling; Armada attrition doctrine (prolonged siege missions)
  Balanced   → Normal cadence
```

---

## 5. AI Behaviour — De-Embedding from the Graph

This is the part the eco manifold points toward but cannot reach on its own.

In the quantum campaign, **AI unit behaviour is driven by de-embedding the graph**.
The graph encodes the world-state; AI actors read their slice of it and derive their
disposition. Concretely:

```
AI disposition = f( partial_trace(ρ, actor_axes) )

For Armada Taelith forces on Verdance's Ashes:
  - Read Q0 (high ARM weight) → aggressive expansion posture
  - Read Q1 (Taelith/Scholarborne) → prioritise eco build, bot labs, swarm units
  - Read Q6 (contested) → defend existing nodes rather than full assault
  - Read Q7 (depleted Tenebrium) → no T2 energy push; stay T1 eco

For Cortex Mantleguard opportunists:
  - Read Q0 (low COR weight) → probe, don't commit
  - Read Q1 (Concordat) → fortified responses, artillery placement
  - Read Q6 (contested) → seize uncontested zones, hold them

For Ashwalker/Independent clans:
  - Read Q6 (maximum superposition) → unpredictable; either ally or obstacle
  - Read clan reputation scalar → ally if > 60, hostile if < 20
```

Each AI "personality" is a **projection operator** on the density matrix. The AI doesn't
need a hand-scripted behaviour tree — it samples its relevant axes and emits a disposition
vector: `{ ecoAggression, militaryAggression, expansionTarget, unitPreference }`.

### Unit Preference De-Embedding

```
unitPreference = argmax over unit roster of:
  classifyEvaluation( evaluate(unit, effectiveState, biomeModifiers) )

subject to faction filter:
  Armada Taelith → prefer 'eco', 'factory-bp', swarm units
  Cortex Mantleguard → prefer fortifications, artillery, 'build-power'
  Ashwalkers → prefer 'eco' when stable, 'strategic' when desperate
```

This means the same scoring logic that powers the player-facing eco manifold also drives
AI build orders — they are literally running the same `evaluateCandidates` query under
different effective states and faction filters. The AI isn't scripted; it's the graph
reading itself.

---

## 6. The Three Victory Paths

### Path A — "Return to the Horizon" (Armada alignment)
Work with Armada forces, restore Taelith governance. Bittersweet — stable but absorbed.

- **Victory:** Control >60% strategic zones AND hold Taelith Command Relay for 20 min
- **Graph effect:** Q0 → ARM eigenstate; Q6 decreases; clan reputation irrelevant
- **Eco condition:** μ > 30 M/s sustained for the final 10 minutes

### Path B — "The Ashes Hold" (Free Space)
Expel both factions, hold the Verdance Broadcaster, declare sovereignty. Hard mode.

- **Victory:** Destroy Armada Command Node AND Cortex Forward HQ; hold Broadcaster 10 min
- **Graph effect:** Q0 collapses to Independent eigenstate; Q1 becomes irrelevant;
  new "Free Space" node appears on galaxy map at Verdance's Ashes position
- **Requirement:** clan reputation > 60 throughout

### Path C — "The Jump" (Escape to Terminal Verge)
Decide the planet is unwinnable. Accumulate Metal, build 3 Jump Spires, charge with Energy,
execute breakout under assault. Unlocks Halecrown chapter.

- **Victory:** 3 Jump Spires fully charged simultaneously, survive launch wave
- **Eco condition:** η (net horizon EV) must be positive for 3 consecutive missions
  before Jump Spires become buildable — the graph enforces that you cannot escape
  from a collapsing economy, only from a stable one
- **Graph effect:** Verdance reverts to contested (neither faction won); Ashwalker
  node appears on Terminal Verge as new moving faction; Q6 for Verdance resets to 0.85

---

## 7. Mission Generation Algorithm

Each mission is sampled from the current ρ and the player's economic state.

### Input Vector

```
missionSeed = {
  Q6_value:          current contested level (0–1)
  P3_stability:      current zone stability (0–1)
  activeZone:        current biome zone (P2 — determines terrain template)
  μ:                 current metal income
  ε:                 current energy income
  β:                 current build power
  φ_progress:        campaign time elapsed (escalation)
  factionPressures:  { armada, cortex, clans, nullmercs }
  playerReputation:  { armada, cortex, clans }
}
```

### Mission Type Sampling

```
if μ < 10:                          → emergency reclaim (The Scar or Ashfields)
elif factionPressures.clans > 0.7
     AND reputation.clans < 40:     → clan confrontation (Verdant Canopy)
elif Q6_value > 0.8:                → contested hold (any zone)
elif P3_stability < 0.3:            → infrastructure crisis (Scaffold Ruins)
elif φ_progress > 0.6
     AND path == C:                 → Jump Spire assault defence
else:                               → weighted sample from zone archetypes
```

### Zone Archetypes

| Zone | Mission types | Eco character | Enemy mix |
|------|--------------|---------------|----------|
| Verdant Canopy | Protect escort, clan rescue | Low BP (dense terrain) | Armada swarm units; clan ambush |
| Ashfields | Reclaim hold, mex rush | Reference state | Mixed; first contact |
| Scaffold Ruins | Capture sabotage, grid repair | Energy penalty | Cortex fortified; chokepoints |
| Surge Flats | Expand race, naval | Flood timer | Fast Armada hover units |
| The Scar | Assault survive, reclaim race | High spot, low BP | Heavily entrenched; wreckage fog |

---

## 8. Named Characters

**The Commander (player)** — Void-touched; recently severed from Directorate or House.
Neither faction confirms their existence. The player decides who they were.

**Sev** — Null-Merc quartermaster. Not Void-touched. Extremely practical. Provides mission
briefings. Her willingness to attempt Path B or C depends on the player's reputation with
her — tracked as a hidden scalar that responds to how the player treats clans and defectors.

**The Broadcaster** — Anonymous voice of the Verdance resistance; transmits from an unknown
location in the Verdant Canopy. The player never meets them. Their transmissions bracket
each mission. Their signal *strengthens* as Q6 shifts toward Independent — the graph
directly drives the narrative ambient layer.

**Taelith Overseer** — The Armada Commander nominally running the Verdance campaign. Neither
villain nor ally. A bureaucrat trying to hold a world with insufficient resources. Becomes
ally in Path A, obstacle in B and C. Her resource state (μ, ε, BP) mirrors the player's
eco manifold — she is running the same build decision math under the same biome pressures.

**Rhekk** — Clan elder, largest Ashfield enclave. Face of what the planet fights to protect.
Survival or death depending on player choices is the key Path B branch point. His faction
pressure scalar feeds directly into Q6 — if he dies, Independent weight drops 0.15.

---

## 9. The Lore Tour — Graph Axes Introduced per Act

| Act | Location | Axes taught | Lore concept |
|-----|----------|------------|--------------|
| Opening | Ashfields | Q0, Q6 | The Ashen Accord; what Line Worlds are |
| Early | Verdant Canopy | P2, Q1 | Taelith terraforming; Biogenesis doctrine |
| Mid | Scaffold Ruins | P3, ε threshold | What happens when faction infrastructure fails |
| Mid | The Scar | φ, η | The Severance War; net horizon value of ruins |
| Late | Surge Flats | μ, β | Full eco manifold; what BAR's economy actually is |
| Path C only | Halecrown | Q7 | Tenebrium; what the factions truly fight over |

---

## 10. The Meta-Campaign Layer (Multiplayer Integration)

Verdance's Ashes world-state is shared across all players in the meta-campaign.
Each standard PvP match played on Verdance's Ashes maps contributes to the global ρ:

```
Armada win:         Q0 += 0.05 toward ARM eigenstate
Cortex win:         Q0 += 0.05 toward COR eigenstate
Ashwalker win:      Q6 -= 0.03 (world stabilises toward Free Space)
                    clan reputation global scalar += 0.02

Eco outcomes fed from match telemetry:
  Average μ across match → updates Q7 (metal pressure reading)
  Match duration         → updates φ (process-time advances)
  Commander deployed     → flags that world is "hot" (escalation +1)
```

The density matrix ρ is a **live object**. Lore events (Broadcaster transmissions,
faction dispatches, new zone unlocks) fire at threshold crossings. Players can see the
current world-state. The campaign and the multiplayer game are the same system.

---

## 11. Connection to the Eco Manifold (Classical ↔ Quantum Bridge)

The classical ROI manifold (bar-eco-manifold) remains valid within this system.
It operates as the **inner loop** of the mission evaluator:

```
quantum graph  →  mission seed  →  biome modifiers
                                        ↓
                              effectiveState (μ, ε, β, storage)
                                        ↓
                        classical manifold scoring
                        (netHorizonEV, payback curves, waterfall)
                                        ↓
                            build order recommendation
                                        ↓
                         AI disposition vector (for AI actors)
                         player build picker (for human player)
```

The quantum graph determines *which* classical manifold the player is on.
The classical manifold determines the optimal actions *within* that manifold.
Neither can replace the other.

**Future migration path:** As the quantum graph matures, the classical scalar eco variables
(μ, ε, β) can be promoted from scalars to quantum observables — expectation values of
measurement operators on the density matrix. At that point the two systems fully merge.
The eco manifold becomes the classical limit of the quantum campaign graph, recoverable
by partial-tracing out all faction/lore axes.

---

## 12. Next Development Steps

### Immediate
1. Define biome modifier vectors for all 5 zones (Table in Section 2 is a starting draft)
2. Write `effectiveState` transform function (Section 4) — the bridge code
3. Draft `missionSeed` generator that reads current ρ values
4. Write 4–5 Broadcaster transmissions (opening cinematic layer)

### Near-term
5. Ashwalker unit roster — what's available at start vs unlocked through play
6. Jump Spire mechanic detail (Path C prerequisite; η-gated construction)
7. AI disposition vector spec — how `classifyEvaluation` maps to unit preference

### For the BAR dev team
- The quantum graph is a **world-state layer above campaign scripting**
- Missions read current Q6, P3, μ, ε values — they do not need to know graph internals
- The graph makes the campaign **replayable** — same planet, different ρ₀, different story
- The meta-campaign makes the world **live** — PvP matches have narrative weight
- The AI build logic **reuses the same scoring engine as the player** — no separate scripting
- The whole system is **sparse** — most axes are unresolved until a zone becomes active

---

*Draft 0.2 — revised from eco manifold source code inspection, June 2026*
*Quantum graph architecture: density matrix world-state model*
*Classical eco bridge: inspired by bar-eco-manifold (netHorizonEV, biome modifier seam)*

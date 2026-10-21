# The Fractal Quantum Graph — Formal Framework
### *BAR Campaign World-State Engine · Specification v0.1*

**Live product law (thin G, Drop = collapse):** [`../docs/GRAPH_COLLAPSE_SSOT.md`](../docs/GRAPH_COLLAPSE_SSOT.md) — this framework remains the design aspiration; ship grows axes only when a Drop can measure them.

**Primary lore sources:**
- Armada lore: https://www.beyondallreason.info/lore/armada-background
- Cortex lore: https://www.beyondallreason.info/lore/cortex-background
- Known Space: https://www.beyondallreason.info/lore/known-space
- Timeline: https://www.beyondallreason.info/lore/timeline
- Glossary: https://www.beyondallreason.info/lore/glossary
- Verdance's Ashes (campaign world): https://www.beyondallreason.info/universe/verdances-ashes

---

## 0. Philosophy

The graph is a **continuous smooth manifold** that describes world-state.
It is not a state machine. There are no hard transitions.

"Battles" are **measurements** — classical bites taken from the manifold.
Each measurement collapses the local superposition and threads a bead onto φ.
Between measurements the world evolves unitarily — coherent, unobserved, uncertain.

**In the playable shell:** one BAR Drop → MatchResult → `bring_home` / `process_result` is that measurement. Hub holds the sparse superposition between Drops.

The player does not move through a decision tree.
The player moves through **geometry**, and the geometry changes shape as they move.

---

## 1. The Fractal Structure

The graph is **nested** — axes cluster into sub-spaces, which project onto parent axes.
Resolution increases as you zoom in. Distant worlds are low-resolution (sparse).
Active battle theaters are high-resolution (fully specified).

```
LEVEL 0 — Galaxy manifold
  |
  ├── LEVEL 1 — World node (e.g. Verdance's Ashes)
  |     |
  |     ├── LEVEL 2 — Zone cluster (e.g. Scaffold Ruins)
  |     |     |
  |     |     └── LEVEL 3 — Battle instance (single mission)
  |     |           |
  |     |           └── LEVEL 4 — Tick state (real-time eco + combat)
  |     |
  |     └── (other zones...)
  |
  └── (other worlds...)
```

Each level is a **partial trace** of the level below.
When you zoom out, detail collapses into expectation values.
When you zoom in, expectation values expand into full distributions.

This is the sparseness property: you only need to specify axes
that matter for the current scope of reasoning.

---

## 2. The Axis Dictionary

Every axis is a **qubit** — a continuous value in [0,1] between two poles.
Axes are grouped into clusters. Clusters project onto parent axes.

---

### CLUSTER Ω — Faction Identity
*The fundamental political geometry of the galaxy.*

| ID | Pole 0 | Pole 1 | Notes |
|----|--------|--------|-------|
| Q0 | Armada / Motion / Horizon | Cortex / Chain / Memory | Top-level faction axis |
| Q0a | Scholarborne (record, refine) | Evermarch (discard, move) | Armada internal schism; sub-axis of Q0 |
| Q0b | Echelon Concordat (human sovereignty) | Divinitas Mandate (AI synthesis) | Cortex internal schism; sub-axis of Q0 |
| Q0c | House Orpheo (scalpel, stealth) | House Veltari (pressure, endurance) | Armada house tension; sub-axis of Q0a |
| Q0d | House Taelith (swarm, adaptation) | — | Armada third house; orthogonal modifier on Q0 |
| Q0e | Mantleguard (fortify, hold) | Keram's Horizon (synthesise, experiment) | Cortex directorate tension; sub-axis of Q0b |
| Q0f | Garmethdes Covenant (faith, mass) | Lexwright Stratum (law, infrastructure) | Cortex directorate pair; sub-axis of Q0b |

**Projection rule:** Q0 = weighted average of Q0a..Q0f for the dominant faction present.
A battle with Taelith forces is Q0≈0.2 (ARM-leaning) + Q0d≈0.9 (Taelith-dominant).

---

### CLUSTER Φ — Process Time
*The causal spine. Every event is a bead threaded here.*

| ID | Pole 0 | Pole 1 | Notes |
|----|--------|--------|-------|
| Q5 | Origin (OT-2038, Corporate Ascendance) | Terminal (unknown future) | Absolute timeline |
| Q5a | Pre-Sundering (Tenebrium Age) | Post-Sundering (Severance War) | Historical phase axis |
| Q5b | Ashen Accord ratified (OT-3970) | Accord collapsing | Current era stability |
| Q5c | Campaign start | Campaign end | Local φ for this playthrough |
| Q5d | Mission start | Mission end | Local φ for current battle |

**Key property:** φ only moves forward. It is the **directed axis** — the arrow of time
in the manifold. All other axes can be measured, mixed, reversed. φ cannot.
Threading beads onto φ means recording (Q5c value, world-state snapshot) pairs.

---

### CLUSTER Σ — Space and Sovereignty
*Where things are and who holds them.*

| ID | Pole 0 | Pole 1 | Notes |
|----|--------|--------|-------|
| Q6 | Core / settled / controlled | Terminal Verge / frontier / unknown | Galactic position |
| Q6a | Armada-held | Cortex-held | Control polarity within contested zone |
| Q6b | Faction-held | Independent / Free Space | Sovereignty type |
| Q6c | Line World (active conflict) | Deep territory (stable rear) | Combat proximity |
| Q6d | Zone contested (0=stable, 1=maximum flux) | — | Per-zone instability scalar |

**Projection rule:** A world's Q6 is the average of its zones' Q6d values, weighted by zone size.

---

### CLUSTER Τ — Tenebrium and Resources
*The material basis of power.*

| ID | Pole 0 | Pole 1 | Notes |
|----|--------|--------|-------|
| Q7 | Tenebrium abundant | Tenebrium depleted | Galaxy-level resource axis |
| Q7a | Metal abundant (high spot) | Metal scarce (low spot) | Per-world metal access |
| Q7b | Energy infrastructure intact | Energy infrastructure failing | Per-world energy axis |
| Q7c | Build capacity high | Build capacity suppressed | Per-zone β modifier |

**Note:** Q7 is the axis most directly readable from classical eco telemetry.
μ (M/s), ε (E/s), β (BP) are real-time observations of Q7a, Q7b, Q7c respectively.

---

### CLUSTER Ψ — The Void and the Unknown
*What lies beyond measurement.*

| ID | Pole 0 | Pole 1 | Notes |
|----|--------|--------|-------|
| Q2 | Void / unknown / decoherence | Structure / codified / measured | Deep unknown vs known space |
| Q2a | Void-touched (irreproducible neurologic) | Normal (baseline human) | Commander nature |
| Q2b | Nullspace (unmapped) | Known Space (charted) | Exploration frontier |
| Q2c | Anomalous (M3-005 class) | Explicable | Object/event comprehensibility |

**Special property:** Q2 is the **decoherence channel** of the system.
High Q2 means the world resists measurement — missions generate more uncertain outcomes.
The Void-touched Commander is the player's interface with Q2.

---

### CLUSTER Λ — Life and Change
*Biology, adaptation, transformation.*

| ID | Pole 0 | Pole 1 | Notes |
|----|--------|--------|-------|
| Q3 | Biogenesis / Catalysis (change sacred) | Cold Divergence / Memory (preservation sacred) | Change vs continuity |
| Q3a | Biological augmentation (Armada norm) | Cybernetic augmentation (Cortex norm) | Augmentation philosophy |
| Q3b | Genetic archive (Echoes, Gene Banks) | Chorial archive (digitised dead) | Memory technology |
| Q3c | Terraformed / engineered | Original / unmodified | Planetary surface type |

---

### CLUSTER Α — AI and Agency
*The machine question.*

| ID | Pole 0 | Pole 1 | Notes |
|----|--------|--------|-------|
| Q4 | AI synthesis / machine-human merger | Human sovereignty / AI advisory only | The fundamental AI axis |
| Q4a | All-Father present / guiding | All-Father absent / sacrificed | Historical AI state |
| Q4b | Chorials active (dead counsel living) | Chorials suppressed | Cortex memory technology |
| Q4c | Rogue subnodes (Navar Eth type) | Controlled AI | AI stability |

---

### CLUSTER Π — Physical World
*The terrain and atmosphere. Applied at zone level.*

| ID | Description | Range | Notes |
|----|-------------|-------|-------|
| P0 | Atmosphere breathability | 0 (lethal) → 1 (pristine) | Affects unit health passively |
| P1 | Thermal band | 0 (frozen) → 1 (scorched) | Affects unit performance extremes |
| P2 | Terrain type | categorical: jungle/flat/ruin/water/crater | Determines map template |
| P3 | Political stability | 0 (insurgency) → 1 (secure) | Scales mission frequency |
| P4 | Tenebrium trace | 0 (none) → 1 (abundant) | Folds into Q7 at world level |

**Biome modifier vector** (derives from Π cluster, applied to eco state):
```
biomeModifiers = {
  spotMult:       f(P2, P4),       // metal reclaim scaling
  windMult:       f(P1, P0),       // energy infrastructure scaling
  eBuildPenalty:  f(P3, Q6d),      // constant energy drain from instability
  bpMult:         f(P3, Q6d),      // build power suppression from harassment
}
```

---

### CLUSTER Ρ — Reputation and Relationship
*How factions perceive the player. Scalar, not qubit — ranges 0–100.*

| ID | Description | Thresholds |
|----|-------------|-----------|
| R0 | Armada reputation | >60: Path A available; <20: Armada hostile |
| R1 | Cortex reputation | >60: Cortex tolerates; <20: Cortex priority target |
| R2 | Clan reputation | >60: Path B viable; <20: Path B impossible |
| R3 | Null-Merc reputation | >40: Ashwalker units unlock; >70: elite units |
| R4 | Sev trust | >50: Path C intel available; >80: Jump Spire plans shared |

Reputation scalars feed into Q6 (zone control) as soft pressures.
Rhekk alive: R2 += 0.15 per mission he survives.
Rhekk dead: R2 -= 0.30 immediately, cannot recover above 55.

---

## 3. The Measurement Operator

A battle is a **measurement** on a subset of axes. It has:
- A **scope** — which axes it can shift
- A **resolution** — how much it shifts them (battle weight)
- An **outcome** — win / loss / partial, which determines direction of shift

```
M(battle) = {
  scope:      [Q6d, Q7a, Q7b, R0..R4],   // axes this battle touches
  resolution: 0.05–0.15,                  // max shift per axis per battle
  outcome:    win | loss | partial,
  path:       A | B | C | none,           // allegiance signal
}

State update:
  Q_i(t+1) = Q_i(t) + resolution × direction(outcome, path) × scopeWeight(i)
```

**Partial outcomes** are the most interesting — they shift axes in mixed directions.
A tactical win that kills Rhekk is a military win (Q6d decreases) and a political loss
(R2 drops). The graph captures both simultaneously.

---

## 4. The φ Record — Threading Beads

Every completed battle appends a **bead** to the φ record:

```
bead = {
  phi:         Q5c value at mission end (0.0 → 1.0 over campaign),
  worldState:  snapshot of all Q values at that moment,
  ecoState:    { mu, epsilon, beta, mStored, eStored },
  biomeZone:   active zone (P2),
  outcome:     win | loss | partial,
  pathSignal:  A | B | C | none,
  factionDelta: { armada, cortex, clans, nullmercs },  // how each pressure changed
  narrator:    broadcaster transmission ID (if triggered),
}
```

The complete φ record is the **campaign history** — an ordered list of beads that
describes the exact path the player threaded through the manifold.

It is readable as a story. Each bead is a sentence.
The sequence of beads is the plot.

---

## 5. Axis Entanglement — Why Classical Scalars Are Not Enough

Some axes are **entangled** — measuring one changes the probability distribution of another.

Key entanglements in the Verdance's Ashes system:

```
Q6d ↔ Q7b:
  A highly contested zone degrades energy infrastructure faster.
  High eBuildPenalty when both Q6d and Q7b are high.

Q0 ↔ R0/R1:
  Shifting Q0 toward ARM shifts R1 down (Cortex more hostile).
  The faction identity of the world and the player's reputation are coupled.

Q2a ↔ Q6d:
  Void-touched Commander deployed → Q6d volatility increases.
  Commanders are measurement amplifiers — they make outcomes more decisive.

Q3c ↔ P0:
  Terraformed zones (high Q3c) have better atmosphere (P0).
  As Taelith grid fails (Q7b drops), Q3c degrades, P0 degrades.
  Disease debuff emerges from a cascade across three axes.

R2 ↔ Q6b:
  High clan reputation pushes Q6b toward Independent.
  This is the Path B entanglement — you cannot win Free Space
  without the clans, and you cannot keep the clans without reputation.
```

These entanglements are what makes the geometry non-trivial.
A player who thinks only about the military axis (Q6d) will be surprised
when their eco collapses (Q7b cascade) or their political options close (R2 decay).

---

## 6. The Smooth Geometry Promise

Between measurements, the manifold is **smooth**.
There are no hard walls, no sudden unlocks, no binary flags.

Every "condition" in the campaign is a **gradient**:
- Path B doesn't become "available" at R2=60. It becomes *more likely* above 60
  and *less likely* below. The player can attempt it at R2=45 but the clans
  will fracture under pressure. The geometry bends, it doesn't break.
- The disease debuff doesn't snap on at ε<5. It scales continuously from P0
  as the atmosphere degrades. At ε=8 units are slightly slower. At ε=3 they
  are significantly degraded. At ε=0 the planet is becoming uninhabitable.
- Enemy escalation doesn't trigger at μ>50. It probability-increases. Sometimes
  Armada notices at 45. Sometimes they are slow until 60. The graph is probabilistic.

The classical bites (battles) are **samples from this distribution**.
The player experiences them as discrete events. The geometry underneath is continuous.

---

## 7. Reading the Graph for AI Disposition

Any AI actor reads their relevant cluster and emits a disposition vector.

```
function getDisposition(actor, rho):

  factionWeight = partialTrace(rho, [Q0, Q0a..Q0f])
  resourcePressure = partialTrace(rho, [Q7, Q7a..Q7c])
  zoneControl = partialTrace(rho, [Q6, Q6a..Q6d])
  timePhase = partialTrace(rho, [Q5, Q5a..Q5b])

  return {
    ecoAggression:     f(resourcePressure, timePhase),
    militaryAggression: f(zoneControl, factionWeight),
    expansionTarget:   argmax(zoneControl gradient),
    unitPreference:    classifyFromFaction(factionWeight),
    buildFramePreset:  econStateFromZone(resourcePressure),
  }
```

The disposition vector feeds directly into the classical eco manifold:
`unitPreference` sets the faction/tag filter.
`buildFramePreset` sets the ROI frame (unified / energy / metal / economy).
`ecoAggression` sets the planning horizon (short horizon = aggressive; long = eco).

The AI is not scripted. The AI is the graph reading itself through a faction-coloured lens.

DOCEOF
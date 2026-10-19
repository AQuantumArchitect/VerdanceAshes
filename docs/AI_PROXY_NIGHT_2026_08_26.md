# AI proxy night — 2026-08-26

Overnight session: drive the game with AI proxy players (SimpleAI / BARbarIAn
hard / BARbarIAn hard_aggressive), tinker with the umwelt-inspired proxy, and get
a real feel for how the map zones feed each other — with an eye on closing the
gap between the abstraction engine and actual unit instantiation.

Everything below is measured on this machine tonight unless marked otherwise.
Nothing is committed; the working tree carries the changes.

---

## Headline findings

All the same shape: **the repo already holds the data that would prevent the bug,
and nothing checks it.**

1. **The "player" team cannot build anything with build power.** The campaign's
   Tenebrium gate throttles `playerTeamID`, and no scenario in the repo funds it.
2. BARbarIAn is seated on a faction it has no build chain for, on every map.
3. Three of seven maps start the two sides on ground that is not symmetric.

(1) and (2) land on the *same team* in the `campaign_ai` baseline suite, which is
the project's AI calibration corpus. That corpus has been measuring an AI that can
neither build nor use its faction.

---

## Headline 1: the player team is build-locked in every AI scenario

`gadget:AllowUnitCreation` delegates to `tenebLoot.allowCreate`
(`include/va_tenebrium_handlers.lua:415-437`). For `builderTeam == playerTeamID`
only:

```lua
if (tenebLoot.bank or 0) < cost then return false end          -- blocked
local maxBp = tenebLoot.maxPlayerBuildPower()                   -- 150 * accessTnb
if maxBp <= 0 or (used + bp) > (maxBp + 0.01) then return false end
```

The code comment states the failure mode outright:
*"Bank 0 + no invested => maxBp 0 => block."*

`startBank` comes from `mission.tenebrium.playerBank / .bank / commerce.tenebrium`
(`:139`). **No scenario file in the repo sets any of them** — not
`data/scenarios/authored/`, not `data/scenarios/campaign_ai/`, and not my duel set
before I found this. So the bank is 0, the build-power ceiling is 0, and every
constructor, factory and nano the player team's AI tries to build is refused.

Measured, one Rock Jungle run before the fix: **345 `VA_TENEBRIUM_BLOCKED need=1
have=0` lines**. The consequence, SimpleAI mirror match, total unit value:

| game min | team 0 (player, throttled) | team 1 | team 2 (raptors) |
|---:|---:|---:|---:|
| 3 | 3 560 | 4 766 | 50 000 |
| 8 | 4 240 | 9 638 | 100 500 |
| 21 | **3 770** | **34 925** | 232 933 |

Team 0 is flat for twenty-one minutes — it never builds a single thing — while an
identical AI on the other side grows ninefold. That, not the map and not the
faction, is why team 0 lost every mirror match on every map.

Fix for the duel matrix: stamp `missionBase.tenebrium.bank = 2000` so a duel
carries no campaign economy gate. Verified — the same run now logs **0** blocked
lines. A duel is not a sortie and should never have inherited that gate.

For the campaign suites this is your call, not mine: either fund the AI baseline
scenarios the same way, or exempt profiling runs from the gate in the gadget. What
should not stand is the current state, where the calibration corpus silently
measures a team that cannot build.

---

## Headline 3: three maps start the two sides on unequal ground

Every authored scenario hardcodes a diagonal start pair — team 0 at
`(0.16, 0.16)`, team 1 at `(0.84, 0.84)`. That is a fair pairing only if the map's
symmetry group actually contains a diagonal or a 180-degree rotation. On a map
whose accepted symmetry is a **north-south mirror**, the counterpart of the
northwest corner is the **southwest** corner — and the diagonal drops the two
teams on completely different ground.

The zone cartographer already records both halves of the check: each map's
accepted symmetry group, and a `symmetryFamily` tag pairing every zone with its
counterpart. Greenest Fields:

| family | zones | cells each |
|---|---|---:|
| F1 | GF_NW_MUSTER ↔ GF_**SW**_MUSTER | 392 |
| F2 | GF_NE_PLATEAU ↔ GF_**SE**_PLATEAU | 1740 |

Team 0 starts in `GF_NW_MUSTER` (F1, 392 cells, relative height 0.22). Team 1
starts in `GF_SE_PLATEAU` (F2, **1740 cells**, relative height 0.72). Different
families — **4.4x the area, on high ground**.

Across the pool:

| map | accepted symmetry | team 0 start | team 1 start | |
|---|---|---|---|---|
| greenest_fields | `mirror_ns` | NW_MUSTER (F1, 392) | SE_PLATEAU (F2, **1740**) | ✗ 4.4x area |
| ancient_bastion | `mirror_ns` | NW_BASTION (F10, 478) | SE_RESERVE (F8, **1702**) | ✗ 3.6x area |
| all_that_simmers | `rot180` | NW_SHORE (relH 0.23) | NE_PLATEAU (relH **0.59**) | ✗ height, and both starts are northern |
| eye_of_horus | `rot180` | NW_BASTION (F4) | SE_BASTION (F4) | ✓ |
| koom_valley | all three | NW_MUSTER (F16) | SE_MUSTER (F16) | ✓ |
| tabula | `rot180` | NW_OUTER_RESERVE (F1) | SE_OUTER_RESERVE (F1) | ✓ |
| the_rock_jungle | `rot180` | NW_OUTER_MUSTER (F1) | SE_OUTER_MUSTER (F1) | ✓ |

The diagonal happens to land on true counterparts for the four `rot180` maps.
It fails on both `mirror_ns` maps, and on All That Simmers, whose bases are
`(0.14, 0.14)` and `(0.82, 0.14)` — both in the north, which no symmetry group
makes equivalent.

### What the mirror matches showed — and what they turned out to mean

Three AI mirror matchups on Greenest Fields — identical AI on both sides, fixed
RNG seed, 21 game-minutes:

| mirror | ratio team0/team1 | crossings | verdict |
|---|---:|---:|---|
| BARb aggressive | 1.014 | 0 | tie |
| BARb hard | 0.430 | 66 | team 0 stalled |
| SimpleAI | **0.000** | 74 | **team 0 annihilated** |

Monotonic in contact, and I initially read that as the positional disadvantage
cashing out: the aggressive mirror "ties" only because neither side ever leaves
home. That reading was wrong — see below.

### Correction: the mirror results do NOT demonstrate this

I ran a side-swap control — `greenest_fields.sideswap.json`, byte-identical
except team 0 becomes Cortex and team 1 Armada — and got:

| team 0 faction (at NW_MUSTER) | team 1 faction (at SE_PLATEAU) | ratio at 21 min |
|---|---|---:|
| Armada | Cortex | 0.000 |
| **Cortex** | **Armada** | 0.448 |

Team 0 lost both times, and I concluded the disadvantage travelled with the start
position. **That conclusion was wrong, and the control was not a valid one.**

Both arms held `playerTeamID = 0` fixed — and as the next section shows, the
campaign's Tenebrium gate blocks the *player team* from building any build-power
unit when its bank is zero, which every scenario in this repo leaves at zero. So
both arms carried the same throttle on the same team. "Team 0 loses either way" is
exactly what a player-team throttle predicts, and it is equally consistent with
the start positions being perfectly fair.

The 12 runs completed before the throttle was found are archived at
`reports/map_surveys/ai_duel_suite_tenebrium_confounded.json`. They are good
evidence of the bug and unusable as AI comparisons.

### Re-run with the throttle removed

Same six pairings on Greenest Fields, `tenebrium.bank = 2000`, everything else
identical:

| mirror (identical AI, fixed seed) | before | **after** |
|---|---:|---:|
| BARb aggressive | 1.014 | **0.516** |
| BARb hard | 0.430 | **0.723** |
| SimpleAI | 0.000 | **0.000** |

All three mirrors still favour team 1. At this point I took that as the position
finding confirmed. Koom Valley then said otherwise.

### Final: all 42 runs, 7 maps

The matrix completed — 42/42, 0 failures, 4h59m. Mirror ratios (team 0 / team 1),
against the start-symmetry check:

| map | check | BARb agg | BARb hard | SimpleAI | verdict |
|---|---|---:|---:|---:|---|
| greenest_fields | ✗ fail | 0.516 | 0.723 | 0.000 | **team 1 sweeps** |
| ancient_bastion | ✗ fail | 1.379 | 2.544 | 0.902 | mixed |
| all_that_simmers | ✗ fail | 0.697 | 1.211 | 1.292 | mixed |
| eye_of_horus | ✓ pass | 1.026 | 1.384 | 0.000 | mixed |
| koom_valley | ✓ pass | 0.133 | 0.000 | 0.000 | **team 1 sweeps** |
| tabula | ✓ pass | 2.036 | 1.974 | 1.329 | **team 0 sweeps** |
| the_rock_jungle | ✓ pass | 1.529 | 1.168 | 0.396 | mixed |

**The symmetry check does not predict mirror bias.** Of the three maps that fail
it, one sweeps. Of the four that pass, two sweep — in opposite directions. The
check remains a valid statement about zone data and a useless predictor of
balance.

Three maps are badly side-biased and they are not the three the check flags:
Greenest Fields and Koom Valley hand every mirror to team 1, Tabula hands every
mirror to team 0.

Also visible: **SimpleAI mirrors collapse to 0.000 on three maps**. A mirror
between two identical SimpleAIs is the least stable configuration in the set —
whichever side gets ahead appears to run away completely.

### Second correction: the symmetry check does not predict the bias

After Rock Jungle came in I wrote that it was a clean positive control — mirrors
scattering around 1 on a map that passes the start-symmetry check, against a
consistent bias on the map that fails it. Koom Valley then finished and broke that
story.

All three completed maps, mirrors only (identical AI, fixed seed, no throttle):

| map | start-symmetry check | BARb agg | BARb hard | SimpleAI |
|---|---|---:|---:|---:|
| greenest_fields | ✗ **fails** | 0.516 | 0.723 | 0.000 |
| koom_valley | ✓ passes | **0.133** | **0.000** | **0.000** |
| the_rock_jungle | ✓ passes | 1.529 | 1.168 | 0.396 |

Koom Valley passes the check and is the **most** team-1-biased map of the three —
more extreme than the map that fails it. One passing map balanced, one passing map
lopsided. The check does not predict mirror balance, and my "positive control"
reading was one favourable sample.

Ruled out as causes, by measurement rather than argument:

- **Build throttle** — 0 `VA_TENEBRIUM_BLOCKED` lines in these runs.
- **Tech gate** — the second player-team gate in `AllowUnitCreation`; no
  `VA_TECH_GATE` line, so `techGateEnabled` is false (the duel seeds carry no
  `techPolicy`).
- **Faction** — team 0 is Armada on all three maps, yet Rock Jungle favours team 0.
- **Map aspect** — Koom Valley (12288x8192) and Rock Jungle (10240x8192) are both
  non-square and disagree.

What is left is something the zone-level check does not see — metal-spot
distribution near each start is the obvious candidate, since balance is decided at
spot granularity and my check compares zone area, family and height. I did not get
to test it.

**The finding that stands, and it is the useful one:** AI-vs-AI duels on these maps
carry a large side bias — on two of three maps, team 1 wins every mirror, sometimes
totally. Any A/B comparison run on a single side is measuring the side as much as
the seat. Mirror matches cost one run per pairing and are the cheapest possible
detector for this; they should be standing practice in any calibration suite, and
asymmetric pairings should be run side-swapped and averaged.

The start-asymmetry finding in this section remains true as a **statement about
the map data** — GF_NW_MUSTER really is an F1 zone of 392 cells paired against an
F2 zone of 1740 — and is worth fixing on its own terms. It is simply not what the
mirror numbers are measuring.

Peak zone values do converge once both sides can build: NW_MUSTER reaches 11 000
against SE_PLATEAU's 12 620, where under the throttle it was 5 236 against 14 475.

`tools/verify_start_symmetry_v1.py` (new) checks every scenario's two starts land
in the same `symmetryFamily`, and reports the area ratio and height delta when
they do not. Current run: **10 scenarios fail** across the authored, campaign_ai
and ai_duel sets — the three maps above, in each directory.

**Consequence for everything measured before tonight:** on those three maps, any
A-vs-B comparison is confounded by which side each seat drew. It is not a small
effect — it is the difference between a draw and a wipeout.

**I have not changed any start position.** Moving a team's base changes every
mission on that map, human ones included, and it is possible the asymmetry is
deliberate (an attacker/defender scenario). The fix, if you want it, is to pair
starts by `symmetryFamily` rather than hardcoding a diagonal.

---

## Headline 2: the AI-vs-AI baseline has been measuring a crippled AI

`engine\AI\Skirmish\BARb\stable\config\*.json` names **369 Armada units and 363
Cortex units. It names zero Legion units.** BARbarIAn has no Legion build chain.

Every authored scenario puts **team 0 on Legion**:

| map | team 0 | team 1 |
|---|---|---|
| all_that_simmers | **Legion** | Armada |
| ancient_bastion | **Legion** | Armada |
| eye_of_horus | **Legion** | Cortex |
| greenest_fields | **Legion** | Cortex |
| koom_valley | **Legion** | Armada |
| tabula | **Legion** | Armada |
| the_rock_jungle | **Legion** | Armada |

`new_campaign_ai_baseline_matrix.ps1` seats BARb hard_aggressive on the player
team and marks `priority = "baseline"` for team 0 only
(`new_campaign_ai_baseline_matrix.ps1:124`). `run_campaign_ai_baseline_suite.ps1`
defaults to `-VariantMode baseline`, which filters to exactly those runs. So the
default campaign-AI baseline suite runs **BARb on Legion, on every map** — an AI
that cannot build anything from its assigned faction.

Measured, greenest_fields, BARb hard_aggressive (Legion, team 0) vs SimpleAI
(Cortex, team 1), 34 game-minutes:

| game min | BARb value | SimpleAI value | ratio | verdict |
|---:|---:|---:|---:|---|
| 3 | 3082 | 5904 | 0.52 | player_stalled |
| 5 | 3082 | 6491 | 0.47 | player_stalled |
| 8 | 3172 | 6904 | 0.46 | player_stalled |
| 13 | 3557 | 9097 | 0.39 | player_stalled |
| 21 | 3957 | 11383 | 0.35 | player_stalled |
| 34 | 3957 | 15481 | **0.26** | player_stalled |

BARb is essentially frozen from minute 3 — 3082 to 3957 over half an hour, while
SimpleAI compounds to 15481. Its unit list at minute 8 was
`legeconv x6, legwin x13, legestor, legsolar x2, legcom, legmstor`: pure economy,
not one combat unit, because it has no Legion recipes to follow.

The suite's own stated target is the exact opposite — `install_playable_slice.ps1:169`:
*"BARb hard/aggressive should clear or gain advantage; SimpleAI should stall."*

**This is the abstraction/instantiation gap in its purest form.** The design says
"seat a strong aggressive AI here to stand in for a good human". The
instantiation produces an AI that cannot play. Nothing in the pipeline notices,
because nothing validates that the seated AI supports the team's faction.

### Fix applied to the new duel matrix, not to the existing suite

`new_ai_duel_matrix.ps1` reassigns the two duelling teams to Armada/Cortex by
default and records `authoredSideA`/`authoredSideB`/`factionsForced` in the
manifest so the substitution is visible. `-KeepAuthoredFactions` reproduces the
defect deliberately.

I did **not** touch `new_campaign_ai_baseline_matrix.ps1` or the authored
scenarios — the Legion assignment may be a deliberate story choice (Ashwalkers as
Legion), and changing which faction the player's stand-in fights as is a design
call, not a bug fix. Options, for you to pick:

1. Keep Legion for the player and stop using BARb as its stand-in (use SimpleAI
   or CircuitAI, which are Lua/generic and do handle it).
2. Keep BARb and move the AI-baseline scenarios to Armada/Cortex, accepting that
   the calibration no longer runs the faction the player actually plays.
3. Add Legion support to a local BARb config fork.

---

## Instrument repairs (all measured before/after)

### 1. Headless runs were dying silently

The first smoke run of the night failed with no result and this, every frame:

```
[Internal Lua error: Call failure] va_tenebrium_handlers.lua:80: Bad teamID in GetTeamUnits
error=2 (LUA_ERRRUN) callin=UnitCreated / GameStart / GameFrame
```

Root cause: the installed seed
(`singleplayer/verdance_ashes/generated/va_current.lua`) is whatever the last run
left there. It held `balance.playerTeamID = 3` from an old Koom Valley survey;
the smoke startscript has only team 0. `game_verdance_campaign.lua` took the
seed's value verbatim, so every `GetTeamUnits(3)` / `GetTeamResources(3)` was a
hard error that killed the callin.

The seed outlives the startscript that produced it, so any matrix that reuses an
installed seed against a different team layout hits this. Fixed by clamping
`playerTeamID` to a team the match actually has, with a `VA_WARN_TEAM` echo when
it substitutes. Two other sites re-read the raw seed value and were pointed at
the clamped one.

Smoke went from *no result, exit 1* to *victory, exit 0*.

### 2. Headless was simulating at 1x real time

Profiling runs ran the sim clock at 1x, so a 21-game-minute milestone cost 21 real
minutes. The shell-bake and cartography gadgets already force `setmaxspeed 20`
for their unattended batches; the campaign gadget did not, and every `va_*` probe
goes through it. Added the same, guarded by the existing profiling condition so a
real session is untouched (`va_headless_speed=0` opts out).

Same scenario, same milestones: **11m31s → 4m00s**. `Speed set to 20.0 [server]`
confirmed in the log. The sim is CPU-bound at roughly 3.5x real time on this box
(~100 fps against a 30 fps clock), not actually 20x.

### 3. Zone flow was structurally unmeasurable

`vaZoneFlow` — described in the code as "the live half of entanglement" — is
populated only by `vaRecordZonePresence`, which was called only from inside
`telemetryJson`, which runs only at export milestones. Five samples across eight
minutes cannot observe a border crossing, and `vaZoneFlow` is reset after every
translation packet, so each packet saw at most one transition per unit. Every
`entanglements` list in every packet was empty.

Added `vaSampleZoneFlow()` on its own clock (default every 150 frames under
profiling), plus a cumulative, never-reset, per-team ledger emitted as
`VA_ZONE_FLOW_JSON` at each milestone and harvested by the profiler into
`zone_flow.json`.

Before: 0 edges. After, at 21 minutes: 27 edges, 83 crossings, with a legible
invasion route.

### 4. The first flow measurements were seagulls

The initial sampler reported crossings between zones no ground unit can move
between — `GF_NE_PLATEAU <-> GF_SW_BASTION`, corner to corner. Team 2 turned out
to be Gaia, holding `critter_gull x8`. BAR's `gaia_critters.lua` spawns wildlife
on the Gaia team; they fly laps over the whole map.

Filtering only inside the sampler was not enough: `telemetryJson` walks *every*
team's units, Gaia included, and calls straight into `vaRecordZonePresence`. The
guard now lives in `vaRecordZonePresence` itself, the single choke point.

### 5. Cross-map travel pointed at zones that no longer exist

The other half of "how zones flow into each other" is the seven `strategic_link`
edges between theatres. The shipped
`luarules/gadgets/include/va_strategic_links.lua` is auto-generated from
`world_zone_graph.v1.json`, but had not been regenerated since the zone-id
migration. All fourteen zone ids in it were dead — the map prefixes themselves had
changed (`KOOM`→`KV`, `TAB`→`T`, `RJ`→`TRJ`):

| shipped Lua (dead) | current graph |
|---|---|
| `GF_SE_STAGING` → `EOH_NW_CRATER_CAMP` | `GF_C_INNER_GATE` → `EOH_NW_BASTION` |
| `KOOM_SE_GREEN_SHELF` → `TAB_NW_PLATEAU` | `KV_SE_MUSTER` → `T_NW_RESERVE` |
| `RJ_SE_JUNGLE_SHELF` → `ATS_SW_ARMADA_LAGOON` | `TRJ_SE_MUSTER` → `ATS_SW_PLATEAU` |

In-engine Mode B travel was offering hops to zones absent from campaign state.
Regenerated with the tool's own `--action emit-lua`; all 14 ids now resolve
(0 dangling, was 14).

The generator's `self-test` should have caught this and did not — it asserted
against those same hardcoded pre-migration ids, so it failed on its *first*
assert and never reached the checks further down. Rewrote it to derive its probe
from the graph and to assert that the shipped Lua references only live zones. It
passes now, and this class of drift will fail loudly next time.

Two of the seven corridors read oddly after the many-to-one migration and are
worth your eye rather than my guess: "Tabula **east** → Rock Jungle" is now
`T_C_SPILLWAY` (the *central* spillway, though `T_E_CAUSEWAY` exists), and
"Bastion → All That Simmers" is now `AB_SE_RESERVE` → `ATS_NW_SPILLWAY`.

### 6. A guard so the faction defect cannot hide again

`scripts/verify_ai_seat_factions.ps1` (new) scans scenario directories and, for
every native AI seat with a discoverable config, checks whether that config names
any unit of the team's faction. Read-only; exits 1 on a confirmed mismatch so it
can gate a suite. Lua AIs (SimpleAI, RaptorsAI, ...) have no config and are
skipped rather than guessed at.

Current output: **79 seats checked, 14 mismatches** — the 7 `campaign_ai`
`player_team_0_aggressive` variants and all 7 `authored_baseline` scenarios. The
new `ai_duel` scenarios come back clean.

---

## At 13 minutes nothing had moved -- and why that was misleading

The first duel at 13 game-minutes, BARb hard_aggressive vs BARb hard_aggressive
on Greenest Fields, both on factions they support:

| team | seat | units at 13 min | where |
|---|---|---:|---|
| 0 | BARb aggressive (Armada) | 41 | **all** in Northwest Muster |
| 1 | BARb aggressive (Cortex) | 24 | **all** in Southeast Plateau |
| 2 | Gaia | 8 | scattered (wildlife, excluded) |

**Zero border crossings.** Not one unit left its start zone in thirteen minutes.

### Correction: that was the build throttle too

I read this as "AI proxies do not leave home at mission timescales" and used it to
justify re-running the matrix at 21-minute depth. The 21-minute depth was the right
call for a different reason, but the reading was wrong.

The same BARb-aggressive mirror on the same map, after the Tenebrium bank was
funded:

| | crossings at 21 min |
|---|---:|
| build-locked player team | **0** |
| funded | **335** |

Team 0 was not choosing to sit still — it could not build anything to move with,
and team 1 had no opponent to advance against. What survives from this section:

- **21 minutes really is the right depth.** Below it, contact is thin regardless.
- **Nothing about AI passivity.** Once both sides can build, the whole zone graph
  is in use by minute 21 — all 22 corridors on Greenest Fields, all 12 zones held.

The 13-minute probe is preserved at
`reports/map_surveys/ai_duel_suite_13min_probe.json` as evidence of the throttle,
not of AI behaviour.

## What the zone flow actually looks like

Greenest Fields, 21 minutes, BARb(Legion, crippled) vs SimpleAI(Cortex).
Cumulative crossings, Gaia excluded (team 1 = SimpleAI, team 0 = BARb):

| corridor | crossings | by team |
|---|---:|---|
| C_INNER_GATE ↔ S_PLATEAU | 12 | SimpleAI 11 |
| NW_BASTION ↔ NW_CITADEL | 11 | SimpleAI 11 |
| SE_PLATEAU ↔ S_PLATEAU | 11 | SimpleAI 11 |
| C_INNER_GATE ↔ NW_CITADEL | 9 | SimpleAI 9 |
| NW_BASTION ↔ NW_MUSTER | 8 | BARb 7 |

SimpleAI's traffic traces one continuous route — **SE_PLATEAU → S_PLATEAU →
C_INNER_GATE → NW_CITADEL → NW_BASTION** — a corner-to-corner invasion across the
map's centre. BARb's only traffic is 7 crossings between two adjacent home zones:
it never left its corner. That asymmetry is the Legion defect *and* the build
throttle, both landing on team 0 at once — not the map.

This run is kept because it is the clearest single picture of what a one-sided
match looks like in the instrument. The numbers below, from the corrected runs,
are the ones to trust.

### With the throttle gone, the whole graph lights up

Six duel pairings on Greenest Fields, 21 game-minutes each, both sides on
factions BARb supports and neither build-locked:

- **All 22 authored corridors carried traffic. Zero inert.** As geometry, the
  adjacency model is not just good — it is fully exercised.
- **All 12 zones were held at some point**, not merely entered.
- **11 unauthored crossings** appeared — zone pairs units moved between that the
  adjacency model does not join. More movement surfaces more routes the geometry
  missed.

For contrast, the same six pairings with the player team build-locked produced
20/22 corridors and 11/12 zones. The throttle was suppressing roughly a fifth of
the map's traffic as well as the balance.

Busiest corridors, summed across the six post-fix runs:

| corridor | crossings | runs |
|---|---:|---:|
| Northwest Bastion ↔ Northwest Muster | 251 | 6 |
| Southeast Plateau ↔ South Plateau | 240 | 6 |
| Northwest Bastion ↔ Northwest Citadel | 234 | 6 |
| Central Inner Gate ↔ South Plateau | 187 | 6 |
| Central Gate ↔ Central Inner Gate | 175 | 6 |
| Northwest Citadel ↔ North Plateau | 127 | 6 |

Every one of these carried traffic in all six runs, which is what makes the
corridor set look well-drawn rather than lucky. The busiest unauthored crossing is
Central Inner Gate ↔ Northwest Citadel at 21 — two zones units clearly move
between that the geometric adjacency does not join.

But occupancy tells a different story from traffic. Peak unit value per zone,
across all six post-fix runs:

| zone | role | peak value | held by |
|---|---|---:|---|
| Southeast Plateau | plateau | **12620** | team 1 |
| Northwest Muster | start | **11000** | team 0 |
| Northwest Bastion | fortress | 3894 | team 0 |
| Northeast Plateau | plateau | 1490 | team 1 |
| Northwest Citadel | citadel | 1156 | team 0 |
| North Plateau | plateau | 910 | team 0 |
| Southwest Citadel | citadel | 630 | team 0 |
| Southwest Bastion | fortress | 550 | team 0 |
| South Plateau | plateau | 300 | team 1 |
| Central Gate | gate | 260 | team 0 |
| Central Inner Gate | gate | 130 | team 0 |
| Southwest Muster | start | 31 | team 0 |

Every zone gets held by somebody, but **the two start zones carry 71.6% of all
peak value**. Expansion beyond them is real and thin — a fortress at 3894, then a
long tail under 1500. Units cross the graph constantly; what they leave behind is
a scattering, not a front.

(Under the build throttle this read as ~90% in two zones with six zones never
occupied at all. Funding the player team moves it from "nothing happens outside
home" to "a little happens outside home". The direction of the observation
survives; its severity was overstated.)

This is still the sharpest version of the abstraction/instantiation gap. The
campaign models zones as *territory that flips* — `zoneMemory[..].control`, front
decay, offscreen clashes converting ground. Over 21 minutes of real fighting,
almost nothing changes hands: the ground each side ends on is overwhelmingly the
ground it started on, plus a thin skirt of outposts. The abstraction's central
noun barely exists in the game yet.

### Rock Jungle behaves completely differently, and that matters

| | Greenest Fields | The Rock Jungle |
|---|---:|---:|
| zones | 12 | 16 |
| corridors live | 22 / 22 | 35 / 36 |
| zones held | 12 / 12 | 16 / 16 |
| **share of peak value in the two start zones** | **72%** | **39%** |

Rock Jungle spreads play across its whole graph — under 40% of value sits at home,
against nearly three-quarters on Greenest Fields. Whatever the campaign's zone
model wants to represent, Rock Jungle already produces much more of it in-mission
than Greenest Fields does.

That is a per-map property worth knowing before tuning anything globally: the two
theatres are not the same kind of space, and a zone mechanic calibrated on one
will not read the same on the other.

### Mirror matchups are a free control worth keeping

Running a seat against itself costs one run per pairing and gives a symmetry check
nobody has to author: identical AI, fixed RNG seed, so anything other than a tie
is an asymmetry in the *setup*, not the AI. It is what caught the build throttle
and what now supports the start-position finding (see Headline 3).

Two lessons from getting it wrong first:

- **A mirror that ties is not automatically a clean bill of health.** The
  aggressive mirror tied at 1.014 under the throttle — by both sides doing nothing.
  Zero crossings. Always read the tie alongside the activity.
- **A mirror only isolates the variable you think it does if everything else is
  actually held.** Mine varied faction while holding player-team *and* position
  fixed, so it could not distinguish the throttle from the ground.

Cheap follow-up still worth running, now that the throttle is off, to separate
faction from position properly — the generator already takes the parameters:

```bash
powershell -File scripts/new_ai_duel_matrix.ps1 -SeatASide Cortex -SeatBSide Armada
```

### On raptor maps, the balance verdict measures raptors

Two of the seven maps carry a RaptorsAI team (`the_rock_jungle` team 2,
`all_that_simmers` team 4). The engine's balance calculation splits the world into
`playerValue` and `enemyValue`, and *everything* that is not the player team lands
in "enemy". The first Rock Jungle run:

| quantity | value |
|---|---:|
| playerValue (team 0) | 2 780 |
| enemyValue (team 1 **+ raptors**) | **270 966** |
| reported valueRatio | 0.0103 |
| duel-only ratio (team 0 / team 1) | **0.089** |

An 8.6x distortion. Raptors also roam: **597 of that run's 934 border crossings
were raptor units**, so the traffic picture was two-thirds wildlife.

`ai_duel_zone_flow_v1.py` now reads the raptor team ids out of the scenario and
excludes them from both figures, reporting a duel-only ratio (team A's value over
team B's, summed from the per-zone buckets) alongside the engine's. On the five
maps with no raptors the duel-only ratio reproduces the engine's exactly, which is
the check that says the correction is sound.

This affects the existing `campaign_ai` suite too — its `wilds`/`raptors` flags
only drive whether a run gets *extended*, not how its verdict is computed.

### Third correction: SimpleAI is the weakest seat, and Greenest Fields is the outlier

On Greenest Fields SimpleAI beat both BARb profiles (1.361, 1.217), and I reported
that as evidence the seat ladder was map-dependent and the pipeline's assumption
suspect. With all seven maps in, that was a single-map artifact.

Does SimpleAI beat BARb? Per map:

| map | simple / BARb agg | simple / BARb hard | |
|---|---:|---:|---|
| greenest_fields | **1.361** | **1.217** | wins both |
| tabula | 0.240 | 1.333 | split |
| ancient_bastion | 0.509 | 0.802 | loses both |
| the_rock_jungle | 0.421 | 0.321 | loses both |
| koom_valley | 0.571 | 0.141 | loses both |
| all_that_simmers | 0.371 | 0.640 | loses both |
| eye_of_horus | 0.000 | 0.000 | loses both |

**One map of seven.** Ladder across all 42 runs, 14 samples per seat:

| seat | mean ratio |
|---|---:|
| BARb hard | 1.699 |
| BARb aggressive | 1.482 |
| SimpleAI | **0.566** |

So the pipeline's target — `install_playable_slice.ps1:169`, *"BARb hard/aggressive
should clear or gain advantage; SimpleAI should stall"* — **is correct**. SimpleAI
does stall against both BARb profiles, on six of seven maps. My earlier claim that
it inverts was drawn from the one map where it doesn't.

What does survive: the *margin* is strongly map-dependent (from 0.000 to 1.361 for
the same pairing), so a single-map calibration will still mis-size difficulty even
though it gets the ordering right. The two BARb profiles are close enough (1.70 vs
1.48) that this data does not separate them confidently.

### Both instruments agree on the weakest seat

| seat | headless, 7 maps (higher = stronger) | abstract proxy win rate vs it (lower = stronger) |
|---|---:|---:|
| BARb hard | 1.699 | 0.119 |
| BARb aggressive | 1.482 | 0.000 |
| SimpleAI | **0.566** | **0.286** |

Both instruments put SimpleAI clearly weakest, by a wide margin, from completely
independent machinery. They disagree on ordering the two BARb profiles, where the
headless margin is small.

That is a real partial cross-validation — unlike the one I claimed earlier, which
was an artifact of the build throttle. Stated at the strength the data supports:
**the abstraction gets "SimpleAI is the weak seat" right, and is not yet shown to
resolve hard vs aggressive.**

### The earlier cross-validation claim was an artifact

Under the build throttle both instruments ranked BARb highest and I called that a
cross-validation. It was coincidence — the headless side ranked BARb high because
the *other* seat was the one that could build. The real, weaker-but-genuine
agreement is in the section above, measured across all seven maps.

---

## The abstraction side

### The proxy modelled two enemy seats; BAR exposes three

`ENEMY_STYLES` in `proxy_campaign_v1.py` had `simple` and `barbarian`
(= aggressive). `install_playable_slice.ps1` exposes `simple`, `barbarian_hard`
and `barbarian_aggressive`. The abstraction could not represent a matchup the
real game can run. Added `barbarian_hard`, gave `--enemy` an `all` option, and
replaced the hardcoded simple-vs-barbarian head-to-head with a general pairwise
ladder that does not silently vanish once a third seat exists.

### The difficulty curve is a cliff, and the seats barely matter

Greenest Fields, abstract proxy, 3 sorties:

| difficulty | simple | barbarian_hard | barbarian |
|---:|---:|---:|---:|
| 1.0 | 1.00 | 1.00 | 1.00 |
| 2.0 | 0.33 | 0.33 | 0.00 |
| 3.0 | 0.00 | 0.00 | 0.00 |
| 5.0 | 0.00 | 0.00 | 0.00 |
| 8.0 | 0.00 | 0.00 | 0.00 |

The proxy wins everything at 1.0 and loses everything at 3.0. Only around 2.0
does the enemy seat change the outcome at all. The `enemy_scale_mul` knobs
(1.05 / 1.25 / 1.45) are swamped by the difficulty multiplier. Any balance
conclusion drawn from the abstract proxy at difficulty 1.0 is reading a saturated
signal.

### Full sweep at the one difficulty that discriminates

All seven maps, difficulty 2.0, 6 sorties x 2 seeds per seat (12 samples each):

| seat | mean win rate | range across maps |
|---|---:|---|
| `simple` | 0.286 | 0.167 – 0.584 |
| `barbarian_hard` | 0.119 | 0.000 – 0.167 |
| `barbarian` (aggressive) | **0.000** | 0.000 – 0.000 |

The ladder is monotonic and matches headless BAR — the new `barbarian_hard` seat
lands where it should, between the other two. Two caveats: the aggressive seat is
pinned at zero on *every* map, so even at the discriminating difficulty it is
still against a floor; and per-map spread is large for an identical seat:

| map | `simple` win rate |
|---|---:|
| tabula | 0.584 |
| eye_of_horus | 0.416 |
| the_rock_jungle | 0.333 |
| koom_valley, greenest_fields, ancient_bastion, all_that_simmers | 0.167 |

Tabula is 3.5x easier than the four hardest maps for the same seat at the same
difficulty. Whether that is intended theatre pacing or uncalibrated drift is a
design question, but it is not currently anywhere in the docs.

Full data: `reports/proxy_seat_sweep_d2.json`.

---

## Structural gaps between abstraction and instantiation

Mapped by reading the pipeline end to end; these are descriptions of the current
code, not changes I made.

1. **Per-zone abstraction collapses to one map-wide number before anything
   spawns.** `zoneMemory[map][zone].abstract` carries seven scalars per zone.
   `expected_map_enemy_scale` sums the presence bands over *every* zone on the map
   into one `{low,center,high}`; the compiler clamps `center` to [3500,11000],
   divides by 6000, and multiplies by a mission ramp. A zone the campaign believes
   is a fortress and one it believes is empty grass produce the same camp at the
   same anchor, differing only by that global multiplier. There is no code path
   where zone A's `baseStrength` adds units to zone A's camp.

2. **Nothing measured in a played mission feeds back.** `logTelemetry()` has three
   call sites, all gated on profiling modoptions or a manual chat command;
   `setTerminal` emits the result JSON and the translation packet but never
   telemetry. So `update_measured_zone_memory` never fires from real play.
   `outbox/bar_zone_telemetry.latest.json` is dated 2026-07-07, and every
   greenest_fields zone in the live state still reads `baseStrength 0.0`,
   `confidence "estimated"`.

3. **Damage to the living shell changes the numbers but never the ground.** The
   shell is ~359 of the ~400 units on greenest_fields — the overwhelming majority
   of what a player actually fights. Shell scars *do* reach the abstraction:
   `capture_node_claims.py` folds them into `zoneMemory[..].abstract.shellScar`
   and heals them over time. But `Build-LivingShellFromTemplate` copies the
   template unit-for-unit, `enemyScale` is not applied to it, and no scar is ever
   subtracted from it. So burning a pocket down moves a scalar in the campaign
   state and re-entry still spawns the identical 359-unit shell.

   Verified live: `state/campaign_state.json` has `persistentBaseSnapshots: {}`,
   `frontEvents: []`, and every greenest_fields zone at `baseStrength 0.0`,
   `militaryPressure 0.0`, `confidence "estimated"`, `control "neutral"`.

4. **Zone-id vocabulary is fractured across three layers.**
   `migrate_zone_ids_v1.py` re-tagged only `pockets[]` in the base templates, so
   `armada_placeholder_v1.json` has pockets on the new ids and `units[]` on the
   retired ones. `va_shell_zone` is therefore stamped with a dead id, the zone
   match in `claimLivingShellObjectives` never fires, and shell scars land on
   zone ids that do not exist in `zoneMemory`.

5. **Two incompatible definitions of "unit is in zone X".** Gameplay decisions
   (objective hold, extraction, beats, continue-camp) use the coarse bounds AABB;
   telemetry uses the exact cell mask. The greenest_fields authored bounds overlap
   heavily, so a zone hold can be satisfied by units standing in a neighbour.

6. **The declared permanence contract is entirely unimplemented.**
   `build_next_mission_v1.ps1:2379-2387` writes
   `continueRules = { carryHeroes, carryCombatUnits, carryWrecks,
   snapDistantUnitsToDeploy, metalCarryFraction, ... }`. A repo-wide grep finds
   each of those five names at **exactly one site — that write**. Nothing reads
   them. `persistentBaseSnapshots` is initialised to `{}` and never written.

   What actually persists: hero XP/wounds, `roster.cadre` counts, and everything
   inside a Mode A same-map continue — and that last one only because
   `setTerminal` skips `Spring.GameOver`, so the Spring match never restarts and
   units persist trivially. There is no cross-process carry of wrecks, structures,
   or standing bases.

7. **The authored zones were cut from a reconstructed prior, not measurement.**
   Every map's `derivedFrom.behaviourSource` is `legacy_prior`. The zone scorecard
   says it plainly: a reconstructed prior "cannot tell a quiet zone from an
   unvisited one". The duel matrix produces exactly the real per-zone
   presence/traffic data the cartographer wants as input.

---

## Safety notes for unattended runs

- **`QBAI_NO_LLM=1` does not fully disable metered API calls.** It has one read
  site (`brain.py:84`) covering only the xAI HTTP path, and it only matters when a
  key resolves — one *does* resolve on this machine from
  `ws-win\yurt\config\yurt.env`. `suite.py` defaults `use_llm=True` and
  `seat.SeatConfig.use_llm` defaults `True`; the `--ant` subscription path ignores
  the variable entirely. I avoided `quantum_bar_ai.suite` (without `--no-llm`),
  `--ant`, and `ant_agent` for that reason. Worth a real guard before any
  unattended gym run.
- **`beat_campaign --train` defaults on and rewrites `app/brain/bar_brain_weights.json`;
  `manifold_gym` saves weights too.** Consecutive overnight runs are therefore not
  independent samples — the proxy drifts as it goes. I backed up `app/brain/` and
  ran the sweep with training off so seat comparisons stay attributable.
- `proxy_campaign_v1.py` runs every campaign in a throwaway temp workspace on a
  fresh state, so `state/campaign_state.json` is never touched. Verified; it was
  also backed up regardless.

---

## What I'd want your call on

Ordered by how much they change, not by how hard they are. I did not touch any of
these — each is a design decision, not a defect.

1. **How AI-vs-AI runs should handle the Tenebrium build gate.** Either fund the
    baseline scenarios (`missionBase.tenebrium.bank`, as I did for the duel set) or
    exempt profiling runs from the gate in the gadget. This is above everything
    else on the list: until it is settled, every AI measurement on the existing
    scenarios is of a team that cannot build, and *my own conclusions flipped*
    once it was lifted — the seat ladder reversed, zero-crossing runs became
    300-crossing runs, and the mirror test only became informative afterwards.

2. **The unexplained side bias.** On two of three completed maps, team 1 wins
    every mirror match — Koom Valley 0.133 / 0.000 / 0.000 despite passing the
    start-symmetry check. Build throttle, tech gate, faction and map aspect are
    ruled out. Metal-spot distribution near the starts is the obvious next
    candidate. Until this is understood, every AI-vs-AI number on these maps is
    partly a measurement of which side the seat drew, and asymmetric pairings need
    running in both directions.

3. **Whether the three lopsided maps are meant to be lopsided.** If Greenest
   Fields, Ancient Bastion and All That Simmers are supposed to be even fights,
   the starts need pairing by `symmetryFamily` instead of a hardcoded diagonal.
   If the asymmetry is deliberate (attacker vs defender), it should be recorded
   somewhere, because right now every tool treats those maps as symmetric. This
    is first on the list because it silently biases every other measurement.

4. **Which faction the player's AI stand-in fights as.** The three options are in
   the headline section. Until this is settled, no AI-vs-AI balance number from
   the existing baseline suite means anything, and re-running that suite would
   just regenerate bad data faster now that the sim clock is fixed.

5. **Whether one map is enough to calibrate a seat.** SimpleAI beats both BARb
   profiles on Greenest Fields by ~3x and loses to both on Rock Jungle by ~3x.
   The existing baseline suite runs one variant per map and the default
   `-VariantMode baseline` filter keeps only team 0. A ranking drawn from that
   will be confidently wrong on some maps.

6. **Whether an AI proxy is a valid stand-in for a player at all, at mission
   length.** A human player under a sortie contract behaves nothing like a BARb
   opening. The proxy is a good instrument for economy and map-shape questions and
   a poor one for "is this mission fun". Worth deciding what you actually want it
   to answer before investing more in it.

7. **Whether per-zone abstraction should reach per-zone spawning.** Right now
   seven scalars per zone collapse into one map-wide multiplier before any unit is
   placed. Making zone A's `baseStrength` size zone A's camp is a contained change
   in `build_next_mission_v1.ps1` — but it is a real difficulty change on every
   existing mission, so it wants your intent and a re-calibration pass, not a
   quiet patch from me overnight.

8. **Whether a played mission should emit telemetry.** One call to `logTelemetry()`
   inside `setTerminal` would make `update_measured_zone_memory` fire from real
   play, which is the whole feedback half of the living world. The cost is an
   extra scan of every unit at mission end. I left it alone because it changes
   what the campaign learns from a human session, which is your call — but of
   everything on this list it is the cheapest large win.

9. **The two odd strategic corridors** named above.

## Suggested order if you want the gap actually closed

The measurement side is now working, so the sequence that makes sense is:

1. Settle the faction question (1), then re-run the AI baseline so the calibration
   corpus is trustworthy.
2. Turn on terminal telemetry (4). That alone gives `zoneMemory` real measured
   values instead of `confidence: "estimated"` on every zone.
3. Only then consider per-zone spawn scaling (3) — it needs measured zone values
   to scale *from*, and until step 2 there are none.
4. Feed the duel matrix's measured presence/traffic back into
   `zone_cartographer_v1.py` to replace the `legacy_prior` behaviour source. The
   zones would then be cut from where armies actually go rather than from a
   reconstruction.

## Files changed

| file | change |
|---|---|
| `mod/.../game_verdance_campaign.lua` | clamp `playerTeamID` to an existing team; force sim speed under profiling; periodic zone-flow sampler; cumulative per-team flow ledger + `VA_ZONE_FLOW_JSON`; Gaia guard |
| `scripts/run_translation_profiler.ps1` | harvest `VA_ZONE_FLOW_JSON` into `zone_flow.json` and `calibration_data.zoneFlow` |
| `tools/proxy_campaign_v1.py` | added `barbarian_hard` seat; `--enemy all`; general pairwise head-to-head |
| `scripts/new_ai_duel_matrix.ps1` | **new** — three-way duel matrix generator, faction-safe |
| `scripts/run_ai_duel_suite.ps1` | **new** — resumable serial matrix runner |
| `tools/ai_duel_zone_flow_v1.py` | **new** — authored adjacency vs measured crossings |
| `tools/proxy_seat_sweep_v1.py` | **new** — abstract seat sweep, training held still |
| `tools/render_zone_flow_page_v1.py` | **new** — survey-plate page of measured traffic |
| `scripts/verify_ai_seat_factions.ps1` | **new** — AI-seat / faction mismatch guard |
| `tools/verify_start_symmetry_v1.py` | **new** — start-position symmetry guard |
| `data/scenarios/ai_duel/greenest_fields.sideswap.json` | **new** — side-swap control scenario |
| `tools/mode_b_reload_travel.py` | self-test derives probes from the graph and rejects dead zone ids |
| `mod/.../include/va_strategic_links.lua` | regenerated from the current world zone graph |
| `data/scenarios/ai_duel/*.json` | **new** — 7 maps x 6 pairings |

Test suite: 336 tests, 3 failures. All three fail identically with my changes
reverted (verified by stashing) — pre-existing, not introduced here:
`test_playtest_infra.KernelSimTests.test_one_sortie_settles`,
`test_theater_home_v083.TestRimStamp.test_midfield_deploy_invalidates`,
`test_verdance_story_engine_v1.StoryVoiceTests.test_intent_carries_briefing_title_and_debrief_candidates`.

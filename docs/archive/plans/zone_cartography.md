# Zone Cartography -- measuring the maps, then re-cutting the zones

> **STATUS (2026-08-25):** the zones are RE-CUT and LIVE. All seven maps now
> carry 12-16 terrain-derived, exactly symmetric cell-mask zones (102 total, up
> from 45 rectangles), promoted through `migrate_zone_ids_v1.py`. Terrain is
> measured at 96x96 (`outbox/terrain_atlas.latest.md`), hydrology is measured per
> map (`data/hydrology/`), and the planet's water cycle is conserved campaign
> state. The density matrix's hydrology anchor and couplings are fixed. 191 tests
> green. **The behaviour survey has still NOT been run** -- every behaviour number
> behind these cuts is a prior reconstructed from June telemetry and is labelled
> `legacy_prior` wherever it appears.

## Why

The 45 zones across the seven maps were promoted from a **single 8x8 grid survey
capped at 2.5 sim-minutes** (2026-06-23). That survey measured base cells and
then *inferred* every lane, rim and gate from the minimap picture -- its own
write-up says so ("likely maneuver lane", "run the next pass at 5-8 minutes").
Zones drive quest archetypes, camp placement, capture geography and the
escalation ladder's targets, so a guess there is a guess everywhere.

## What the evidence already says (baseline, before any new runs)

`python tools/zone_scorecard_v1.py --source legacy` scores the current zones
against every telemetry packet already on disk (June AI-vs-AI surveys plus
campaign runs, 1 to 21+ sim-minutes, all seven maps):

| Map | Zones | Coverage | Dead zones | Failing |
|---|---|---|---|---|
| all_that_simmers | 7 | 94% | 0 | 1 |
| ancient_bastion | 6 | 91% | 0 | 4 |
| eye_of_horus | 6 | 95% | 0 | 3 |
| greenest_fields | 6 | **66%** | **3** | 3 |
| koom_valley | 6 | 94% | 1 | 2 |
| tabula | 7 | 86% | 0 | 2 |
| the_rock_jungle | 7 | 95% | 0 | 2 |

- **17 of 45 zones make a claim the measurement contradicts** -- lanes never
  contested, "starts" nothing is built on, plateaus that are largely water.
- **4 zones are dead ground**: Greenest Fields' two southeast zones measure
  literally 0% occupancy across every sample, and a third sits at 0.2%.
- **Greenest Fields loses a third of its war entirely** (66% coverage): that
  activity happens on ground no zone describes.
- Roles were prose-first: the scorecard found **9 more role names the quest
  generator could not read** (`primary_lane`, `approach_gate`, `legion_start`,
  `defender_start`, `reserve`, `exposed_crossing`, `flank_lane`,
  `secondary_route`, `crossfire_route`) covering **20 of 45 zones**, all
  silently collapsing to the `seize_lane` default -- the same class of bug Drop 4
  fixed for 13 other roles. **Fixed** in `tools/quest_generator_v1.py`.

## What the terrain measures (all seven, 96x96, 2026-08-24)

Full descriptions and relief pictures: `outbox/terrain_atlas.latest.md`
(`python tools/terrain_atlas_v1.py`). Summary:

| Map | Size | Height span | Water | Cliff | Walkable | Largest piece | Metal spots | Starts |
|---|---|---|---|---|---|---|---|---|
| all_that_simmers | 7168x10240 | 482 | 10% | 9% | 84% | 64% | 160 | 15 |
| ancient_bastion | 16384x8192 | 551 | 0% | 10% | 94% | 94% | 96 | 5 |
| eye_of_horus | 6144x7168 | 315 | 0% | 17% | 91% | 91% | 46 | 5 |
| greenest_fields | 8192x8192 | 372 | 0% | 0% | 100% | 100% | 0 | 3 |
| koom_valley | 12288x8192 | 804 | 0% | 15% | 89% | 88% | 134 | 15 |
| tabula | 8192x7168 | 721 | 7% | 15% | 83% | 41% | 68 | 15 |
| the_rock_jungle | 10240x8192 | 421 | 24% | 13% | 70% | 15% | 99 | 15 |

Measurement properties worth remembering when reading those numbers:

- **Slope is max-pooled** over each cell's 3x3 subsamples, so "cliff share" is
  an upper bound that falls as resolution rises (48 -> 96 dropped every map by
  3-6 points). It answers "is there anything uncrossable in this cell", not
  "how much of this cell is steep".
- **Connectivity is threshold-dependent on wet maps.** Blocking cells at
  >= 30/60/90% water gives the rock jungle 14/14/37% for its largest walkable
  piece and tabula 39/78/80%. The dry maps do not move at all. The behaviour
  raster -- where tanks actually drive -- is the arbiter, not this model.
- **Resolution changed one answer.** At 48 cells tabula read as one landmass
  (79%); at 96 it splits (41%). The rock jungle was stable (14% -> 15%), so its
  fragmentation is real. Everything is now measured at 96 and
  `spawn_configs.json` bins behaviour on the same grid.

## The instrument

`mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_cartography.lua` -- a
separate gadget (the campaign gadget is at 194/200 Lua locals), armed by
`va_cartography=1`.

- **Terrain raster** (~40s per map): height, slope, water, buildability
  (`Spring.TestBuildOrder`), metal, per-move-class speeds (`Spring.GetGroundInfo`),
  feature mass, plus BAR's own `resource_spot_finder` metal spots, map-authored
  start positions and engine start boxes.
- **Behaviour raster** (accumulated over a match, emitted at Fibonacci
  milestones): presence, structures, losses at the position units died,
  mobile-only traffic, armed-immobile defence, and first-contact frame -- per
  ally team, per grid cell.

`tools/parse_cartography_log_v1.py` turns the infolog into
`data/terrain/<map>.terrain.json` and `data/behavior/<map>/<config>.raster.json`.

## The measurement protocol

Full AI-vs-AI war, deliberately spawned in configurations that make the map
show different faces (`data/cartography/spawn_configs.json`):

| Config | Teams | Sim min | What it exposes |
|---|---|---|---|
| `mirror_1v1` (a/b) | 2 | 21 | canonical front; comparable with June |
| `three_way` | 3 | 13 | contested middles, secondary lanes |
| `adjacent_1v1` | 2 | 13 | which ground becomes the front when the map is folded |
| `four_corners` | 4 | 8 | maximum pressure -- exposes ground the war NEVER uses |
| `center_vs_rim` | 3 | 8 | siege geometry |
| `wilds_on` (ATS, RJ) | 2 + raptors | 13 | hazard territory |

`tools/plan_cartography_runs_v1.py` resolves those rules into real start
coordinates per map (authored starts first; derived buildable/metal-rich anchors
when a config needs more), writing `data/cartography/run_plan.json`:
**44 runs, ~16h wall**, scheduled across three nights and resumable.

```bash
powershell -File scripts/run_zone_cartography_survey.ps1 -Mode terrain
```
```bash
powershell -File scripts/run_zone_cartography_survey.ps1 -Mode behaviour -Configs mirror_1v1 -RegeneratePlan -Resume
```

Acceptance for a usable dataset: every map has a terrain raster plus >= 3
configs reaching >= 13 sim-minutes.

## Symmetry and hydrology (2026-08-25)

**Symmetry.** `tools/map_symmetry_v1.py` scores each map under mirror-EW,
mirror-NS, rot180 and (square maps) both diagonals, over height, water,
buildability and ground speed. Measured:

| Map | Group | Score |
|---|---|---|
| koom_valley | mirror-EW + mirror-NS + rot180 (order 4) | 0.963-0.967 |
| tabula | rot180 | 0.983 |
| eye_of_horus | rot180 | 0.966 |
| the_rock_jungle | rot180 | 0.945 |
| all_that_simmers | rot180 | 0.933 |
| ancient_bastion | mirror-NS | 0.977 |
| greenest_fields | mirror-NS | 0.930 |

Zones are cut on the **quotient** -- one fundamental domain -- and unfolded, so
mirrored zones are exact images rather than two independent cuts that resemble
each other. A region sitting mostly on the axis stays one self-symmetric zone
instead of being split into half-width slivers. Roles are decided per symmetry
family, because no real map is symmetric to the last elmo and the rule chain
would otherwise read a four-fold family as three spillways and a shoreline.

**Hydrology.** Spring has no synced water-level setter, so a rising waterline is
realised by **sinking the world**: `Spring.AdjustHeightMap(0, 0, X, Z, -D)` in
one call drowns everything below elevation D, and because the shift is uniform
no slope and no relative height changes -- only the shore moves. That matters on
Koom Valley, whose lowest ground is 401 elmos above sea level: real water can
never reach it.

`tools/hydrology_v1.py` measures each map's flood response on an **area-quantile
ladder**, so one step of the dial drowns the same share of every map (even
elevation steps are useless: Ancient Bastion's flat middle goes from 1% to 50%
underwater inside two elmos of waterline). Basins are named at full flood and
inherited downward so a beat that says "flood BASIN_C" keeps meaning the same
ground. Per-map **amplitude** is a design dial, not a measurement -- Koom,
Tabula and All That Simmers swing fully; Greenest Fields is a bone-dry metal-free
desert and holds none, so no hydrology role or camp exclusion fires there.

**The planet cycle** (`state.hydrology`) is a conserved quantity travelling
around a ring of maps, one sixth of a turn per mission. Koom runs
0.97 -> 0.78 -> 0.29 -> 0.00 -> 0.24 -> 0.70 over six missions: full basin to
bone dry and back, with 36% of its metal spots surfacing as it drains. A
diffusion model was tried first and rejected -- it equalised in two missions and
then sloshed between whichever pair was marginally off, never touching Koom at
all.

**Inside a mission**, `generate_beats` adds a telegraphed flood or drain on maps
whose water actually swings: a warning bark at 7:00 and the waterline ramp at
7:45, direction following the campaign (a full basin drains, an empty one
fills, a half-full one is left alone).

## The density matrix, repaired

Three defects, all live before this pass:

- `Spring.GetMapWaterLevel()` **does not exist on this engine**. The guarded call
  returned 0, so `H[N+1][N+1]` was pinned at zero and the entire hydrology row
  and column of the matrix carried no information. The waterline is campaign
  state now, and `hydroCoupling` is each zone's *measured* submerged fraction at
  the current level rather than a constant chosen by a prose tag.
- Off-diagonals coupled **every pair of zones by army-value similarity**, so two
  empty zones in opposite corners read as maximally entangled -- and the error
  grew as N^2, which at 102 zones would have been ruinous. Couplings now exist
  only between zones that share a border, weighted by border length, by forces
  present on *both* sides, and by units measured crossing.
- `getZoneHydroType` read prose tags (`swamp`/`flood`/`low`); it reads the
  measured flood curve first.

## The re-cut

`tools/zone_cartographer_v1.py` cuts zones from the rasters:

1. Seeds at what matters -- authored starts, base-mass peaks, loss peaks,
   traffic-without-settling peaks, betweenness chokepoints, and the centroids of
   large regions none of those touched.
2. Cheapest-path region growing, where cost is terrain dissimilarity plus a
   heavy penalty for crossing cliffs and deep water -- so a zone does not leak
   over a ridge.
3. Merging: slivers and **dead ground** fold into neighbours; near-identical
   neighbours fold together; a hard cap of `--max-zones` (12) and a soft target
   of `--min-zones` (6).
4. Roles assigned from measured signature, drawn only from names the quest
   generator can read (`start`, `gate`, `lane`, `main_field`, `fortress`,
   `citadel`, `island_chain`, `plateau`, `rim_control`, `raptor_wilds`,
   `energy_edge`, `flank_pocket`).
5. An **anchor** per zone: buildable, dry, flat ground nearest the behavioural
   centroid -- what camps spawn on. Zones with no such cell are marked
   `campEligible: false` rather than given a fake centre.

Schema 2.0 (`verdance-zone-map/2.0`): run-length-encoded `cells` over a
`cellGrid`, `anchor`, derived `bounds` kept for legacy consumers, and an
`evidence` block per zone recording the numbers that justified it.

Output goes to `data/zone_maps/derived/` (staging).
`tools/migrate_zone_ids_v1.py` then maps old zones to new by activity-weighted
overlap and, on `--apply`, promotes the maps and repoints everything that names
a zone: `zoneMemory` (carrying control), standing sortie/hub orders, living-shell
pockets (re-tagged from where their units actually stand), plus a
`zone_id_migration.json` the world-graph builder uses to re-place the authored
cross-map links. It then rebuilds adjacency and the graph.

## Adoption already wired

- Gadget: `zoneForPosition` is an O(1) cell lookup when a cell mask exists
  (`vaZoneCellIndex`, a gadget-env global -- the chunk stays at 194/200), so
  zone ownership no longer depends on which overlapping rectangle came first in
  the file. `VA_ZONES` now echoes cell coverage.
- Compiler: `Get-ZoneCenter` prefers a zone's measured anchor over the rect
  centre -- the fix for camps spawning on cliffs and in water.
- Engine: `zone_center_norm` likewise.
- Adjacency: `derive_zone_adjacency.py` uses cell contact across *passable*
  ground when cells and terrain exist, rects otherwise (verified byte-identical
  on today's rect maps).
- World graph: carries `anchor`/`evidence`, honours `campEligible` for
  deploy/extract eligibility, and skips authored links whose zones did not
  survive a remap.

## What the flood probe measured (live, 2026-08-25)

`scripts/verify_hydrology.ps1` arms a flood on the installed mission and samples
ground and army on both sides of it. Three runs on The Rock Jungle:

| Run | Waterline | Ground samples | Units | Underwater | Structures |
|---|---|---|---|---|---|
| first (wet landing zone) | 0.72 -> 0.85 | 97/-113/104 -> 95/-115/102 | 29 -> 25 | 25 -> 21 | 8 -> 8 |
| control (no change) | 0.72 -> 0.72 | unchanged | 39 -> 39 | 3 -> 3 | 8 -> 8 |
| treatment (bigger flood) | 0.72 -> 0.95 | 97/-113/104 -> 94/-117/101 | **39 -> 39** | 3 -> 3 | **8 -> 8** |

**The mechanic is safe.** A 3.5-elmo sink -- larger than the first run's -- cost
**zero units and zero structures**. The four losses in the first run were an
artefact of the landing-zone bug below, not of the flood: that run had put the
army into a spillway, so 25 of its 29 units were standing in water before
anything moved. With a dry landing zone the same map reads 3 of 39.

**The terrain really moves**, uniformly, in one `AdjustHeightMap` call over the
whole map, finishing on the frame it was asked to: every sample fell by exactly
the change in how far the world is sunk.

Two real defects were caught here that no offline test would have found:

1. `vaZoneAdjacency` compared zone TABLES rather than ids (`vaZoneCellIndex`
   stores the zone object per cell), which threw inside `GameFrame` and would
   have broken the translation packet on **every** mission with cell-mask zones,
   flood or no flood.
2. The mission was deploying into `TRJ_C_SPILLWAY` -- a zone that floods at
   level 0.5 -- at a waterline of 0.72, so the landing zone was underwater
   before the battle started. `campEligible` could not catch this: it is a
   static property and cannot know the campaign has since flooded the basin.
   Deploy and extraction zones are now chosen against the mission's *current*
   waterline (`zone_is_landable`), with a test asserting the live mission never
   lands in water.

## Verification

Offline (done): 27 tests in `tests/test_zone_cartography.py` -- infolog format
round-trip, cell ownership exclusivity, roles readable by the quest generator,
starts and chokepoint recovered from a fixture with known ground truth, anchors
provably buildable/dry/flat, no dead zones survive, determinism, coverage
scoring, cliff-aware adjacency, and migration (control carried, orders
repointed, shell pockets re-tagged from world positions). 131 existing tests
still pass; adjacency and world-graph outputs unchanged; `va_001` rebuilds
byte-identical and the installed seed still matches.

Live (queued, with the survey nights):
1. Terrain dump per map; sanity-check heights, water and metal spots.
2. One short mission per map after the re-cut: `VA_ZONES ... cells=N` non-zero,
   camps visibly on land, telemetry attributing >= 90% of unit value to a zone.
3. Re-score with `--source raster` and compare against the baseline table above.
4. Then the standing Drop 4 / Drop 3 Wave 1 probes.

## Standing constraints

- Nothing is committed; the owner triggers commits.
- ASCII only in `.ps1` (BOM-less UTF-8 parses as ANSI; an em dash terminates a
  string mid-line -- one was cleaned out of `install_playable_slice.ps1`).
- Campaign gadget: 194/200 locals. New helpers go in as gadget-env globals.
- Survey runs must never leave a result in `inbox/` (phantom campaign advance);
  the runner deletes any it finds.

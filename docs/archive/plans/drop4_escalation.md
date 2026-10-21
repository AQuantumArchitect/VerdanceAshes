# Drop 4 — Escalation Pass (built 2026-08-24)

> **STATUS:** BUILT and offline-verified (112/112 tests across engine, credit,
> and contract suites; m6/m9/m10 probe scenarios compiled and inspected
> end-to-end; the seed chain proven through the installer; real va_001 rebuilt
> and junction-installed under the new pipeline). **Zero live BAR runs yet** —
> Wave 1 below lists the probes to fire when the machine has headroom.

The owner's brief: continuous escalation of mission complexity AND difficulty
from "blow up these nearly defenseless buildings" to late-game chaos.
Territory capture stays the distilled core — one objective per mission early —
but by the end of act 2 missions carry multiple objectives or stronger ones
(up to "clear the board").

## The tooling (built first, as suspected we'd need)

`tools/escalation_map_v1.py` simulates a full campaign offline — materialize
intent → synthesize a full-fidelity clean win → process result → repeat — in a
**sandbox** (junctioned `data/`, empty outbox; the live campaign is never
touched) and renders the per-mission curve: enemy scale (the compiler's REAL
formula, mirrored), objective kind/count/strength, enemy doctrine, waves,
tech policy, roster growth. Chart it any time with:

    python tools/escalation_map_v1.py

Standing output: `outbox/escalation_map.latest.md`.

## What the baseline map showed (why the campaign felt flat)

| M | Kind | Objectives | EnemyScale | Band |
|---|---|---|---|---|
| 1 | seize_lane | 1 | 0.605 | light |
| 2 | seize_lane | 1 | 0.649 | light |
| 3 | seize_lane | 1 | 1.067 | standard |
| 4 | seize_lane | 1 | 1.206 | reinforced |
| 5 | seize_lane | 1 | **2.015** | heavy |
| 6–10 | seize_lane | 1 | **2.145 (flat)** | heavy |
| 11 | finale | 1 | 2.86 | heavy |

- **Difficulty was a cliff then a plateau**: +67% jump at m5, then five
  identical "heavy" missions — zone-memory presence saturates the scale
  formula's clamp by mid-campaign, leaving act 2 zero headroom.
- **Complexity was constant**: one objective, every mission, all acts.
- **Kind was monotone**: 26 zones across all seven maps had roles/tags the
  quest generator's vocabulary didn't know (causeway, island_chain, fortress,
  raptor_wilds, rim_control…) — ALL fell through to the seize_lane default.
- The engine's mission-card scale preview used a stale formula (no pressure
  tier), so the card and the field disagreed.

## The machinery

**One authority: the escalation ladder** — `data/escalation/mission_escalation.json`
(owner-tunable; matching built-in defaults in `tools/escalation_ladder_v1.py`).
Per mission it authors:

- **`scaleWindow [lo, hi]`** — the compiler still computes enemyScale from
  campaign state (presence, craft knobs, merc standing), then clamps into the
  window. Performance moves the needle INSIDE the window; the owner's
  difficulty dial scales the walls themselves (dial 1.25 → both walls +25%).
- **`secondaries`** — side objectives resolved to real zones off the quest
  board at intent time (always distinct from the primary). `required=false`
  is a bonus mark (pays merc standing, +1.5 rep each); `required=true` gates
  victory alongside the primary.
- **`objectiveStrength`** — `surgical` (today's single centerpiece) → `raze`
  (the whole camp joins the objective book — living-shell teeth included) →
  `purge` (clear the board: every armada/cortex team must be emptied).
- **`wavesMode`** — off/light/full override for escalation waves.

The authored curve: m1 [0.35,0.5] single surgical, waves off → m4 +1 bonus
mark, waves light → m6 +1 REQUIRED mark → m8 +required+bonus → m9 RAZE →
m10 PURGE at [1.3,1.7] → finales [1.7,2.6] (their spine machinery untouched).

**Pipeline wiring:**
- Engine stamps `intent.escalationPlan`; briefings gain Ketha lines for
  raze/purge/secondary marks (`briefing.raze/.purge/.secondary_*` pools);
  the card preview now clamps into the same window the field uses; bonus
  secondaries pay out in `process_result` (`secondaryResults` added to
  contract_v2 normalize).
- Compiler (`build_next_mission_v1.ps1`) honors window/waves/strength, places
  `Add-SecondaryObjectiveCamp` at each resolved zone (small works with role
  `objective_secondary` + light garrison, own team, faction-pact-swept into
  the primary's alliance), flips the primary camp garrison to
  `objective_target` under raze, stamps `objective.strength` +
  `missionBase.secondaries` + card lines.
- Installer (`install_playable_slice.ps1`) passes `secondaryId`/`required`
  force fields through its whitelist into the Lua seed.
- Gadget: one new table (`extraObj`, 194/200 locals) books secondary works
  into their own ledger (never the primary pool — a capture clear-fraction
  can't be cheesed with them), `vaAllObjectivesDone()` gates extraction and
  no-extraction victory on primary + required marks + purge,
  `vaCheckPurge` polls the armada/cortex team roster, and the result JSON
  gains `secondaryResults` + `purge`. HUD widget shows the marks (map
  markers + panel lines) and holds the extract prompt until everything
  required signs off.
- Quest generator: 13 new role mappings + 3 new tag mappings (the vocabulary
  fix), plus an anti-repeat penalty (−0.35 for last mission's kind; history
  beads now record `objectiveKind`).

## Two real bugs found by the map tool (both fixed)

1. **Stale Mode A sortie loop** — `materialize_next_intent` persists its
   auto-pick to `outbox/next_sortie_order.json`, but `consume_played_hub_sorties`
   only consumed HUB-stamped orders. Every later mission reloaded the same
   contract (same kind, same zone — even after that zone flipped to the
   player), overriding the quest board forever. Fixed: played Mode A orders
   are consumed too, and materialize discards any standing order whose target
   the patron already holds. (Genuine hub orders for unplayed maps are kept.)
2. **Installer whitelist ate the ledger** — `Expand-ScenarioForces` whitelists
   force fields, so `secondaryId`/`required` never reached the seed; the
   required-mark gate would silently never arm in live BAR. Fixed + proven:
   the installed seed now carries them.

## The curve after (same tool, same sim)

| M | Kind | Objectives | EnemyScale | Band |
|---|---|---|---|---|
| 1 | gate_control | 1 | 0.50 | light |
| 2 | seize_lane | 1 | 0.62 | light |
| 3 | hold_plateau | 1 | 0.75 | light |
| 4 | hold_plateau | 1+1bonus | 0.88 | standard |
| 5 | seize_lane | 1+1bonus | 1.00 | standard |
| 6 | gate_control | 1+1req | 1.12 | standard |
| 7 | seize_lane | 1+1req | 1.25 | reinforced |
| 8 | hold_plateau | 1+1req+1bonus | 1.40 | reinforced |
| 9 | hold_plateau | 1+1req RAZE | 1.55 | reinforced |
| 10 | gate_control | 1 PURGE | 1.70 | heavy |
| 11 | finale | 1 FINALE | 2.60 | heavy |

Strictly monotone (~+0.13/mission), no cliff, no plateau; kinds rotate; zones
flip and get retaken by the world sim (the sim's synthetic wins now carry the
gadget's real capture-claim fields, so the map reflects the living war).

## Wave 1 — prove it live (adds to Drop 3's list; first BAR session)

1. `scripts/verify_secondary_objectives.ps1` — **AUTHORED, not run.** Needs a
   mission-6+ seed (compile from a mid-campaign state). One headless run
   proves: VA_SECONDARY_ARMED → kill primary (`va_test_killobjective_frame`)
   → VA_OBJECTIVE_COMPLETE but NOT all-done → kill marks
   (`va_test_secondary_frame=900`) → VA_SECONDARY_COMPLETE →
   VA_ALL_OBJECTIVES_DONE, with the ordering asserted (that ordering IS the
   required gate).
2. Purge: act-2 m10 seed + manual or scripted board clear → VA_PURGE_ARMED /
   VA_PURGE_COMPLETE before victory.
3. Raze on a living-shell seed: VA_SHELL_OBJECTIVES_CLAIMED count should
   include teeth (razeMode tagging).
4. Everything from Drop 3 Wave 1 (tech gate, hero lifecycle, objective
   automation on the 194-local gadget), and delete
   `inbox/latest_va_result.json` after every probe.

## Standing constraints

- Everything remains UNCOMMITTED until the owner triggers commits.
- Gadget main chunk: 194/200 locals — pack new state into existing tables
  (`extraObj`, `testHooks`, `doctrine`), cold helpers as gadget-env globals.
- The ladder JSON and `escalation_ladder_v1.DEFAULT_LADDER` must stay in
  sync when retuning; `python tools/escalation_map_v1.py` charts any retune.
- The real m1 remains the owner's hub pick (rock_jungle hive-clear at
  window-clamped 0.5 scale) — rebuilt and junction-installed.

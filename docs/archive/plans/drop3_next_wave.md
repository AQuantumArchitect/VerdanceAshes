# Drop 3 — Next Wave Plan (drafted 2026-08-24, after Drop 2 act structure)

> **STATUS (2026-08-24, same-day build):** Waves 2 and 3 are BUILT and
> offline-verified (75/75 engine tests; act-1/act-2/finale compiles inspected;
> real va_001 rebuilt + junction-installed). Wave 1's probe script
> `scripts/verify_tech_gate.ps1` and its gadget hook (`va_test_techgate_frame`)
> are AUTHORED but the live probes have not run — still blocked on BAR
> headroom. Bonus fix while wiring finale camps: same-faction camps were
> mutually hostile (each camp gets its own allyteam and Spring only allies via
> explicit pacts) — the compiler now emits armada↔armada / cortex↔cortex pacts
> and cross-allies everything standing with the player. Everything below is
> annotated inline.

Drop 2 made the owner's three acts mechanically real end-to-end:

- **Act 1 (missions 1–5) — ground control:** warband doctrine, no base laying
  (seed `techPolicy.buildStructures=false`, gadget `AllowUnitCreation` gate).
- **Act 2 (missions 6–10) — constrained RTS:** commander + T1-only building;
  T2/T3 exist on the player side only as granted units (heroes, cadre).
- **Act 3 (missions 11+) — path-keyed finales:** full unconstrained BAR,
  ~95-unit massive start, no extraction, 40-minute clock.
  A=overthrow/ancient_bastion, B=sovereignty/all_that_simmers,
  C=spire_jump/the_rock_jungle.

It also resurrected the campaign gadget itself (Lua 200-local overflow had it
dead since ~Jul 29) and restored the mod junction. **Nothing in this drop has
run in a live BAR yet** — the machine had no headroom to launch the game.

## Wave 1 — Prove it live (first thing when BAR can run; ~1 session)

1. `verify_tech_gate.ps1` headless probe — **AUTHORED, not yet run.** The
   gadget's `va_test_techgate_frame` hook spawns a legck at the deploy beacon,
   echoes `VA_TEST_TECHGATE def=<name> allowed=<bool>` for a 5-def matrix
   (T2 lab / T1 lab / T1 solar / T1 unit / T2 unit), then issues a real T2-lab
   build order for a genuine `VA_TECH_GATE_DENY`. The script derives expected
   verdicts from the scenario's own techPolicy (works on act-1/2/3 seeds) and
   deletes any probe-written inbox result. Resurrect exemption rides
   verify_hero_lifecycle (its rez step runs under act-1 policy).
2. Re-run `verify_hero_lifecycle.ps1` and `verify_objective_automation.ps1` —
   they last passed on the pre-overflow gadget and must pass again on the
   192-local one. Watch for `VA_BRIDGE_LOADED`, `VA_TECH_GATE`, and the
   absence of "more than 200 local variables" / "more than 60 upvalues".
3. Finale probe: act-3 seed + `va_test_killobjective_frame` → expect victory
   via `objective_complete_no_extraction_zone` (no extraction rect path).
4. Delete `inbox/latest_va_result.json` after every probe (phantom-advance
   gotcha).

Acceptance: all probes green on the real engine; then the owner's va_001
playtest is the feel test for Act 1.

## Wave 2 — The hero roster arc (the "12 named heroes" promise) — **BUILT**

1. **DONE** — `data/story/hero_roster.json`: 11 authored heroes on verified
   Legion chassis (rusk/leggat, verse/legjav, mirren/legcen, kettle/legrezbot,
   odessa/legamph, brakhov/leginc, yeva/legaspy, cauter/legshot, grath/legkark,
   halq/legbal, auditor/legeallterrainmech). Merged locked by `ensure_roster`.
   **Owner review of names/fictions still wanted.**
2. **DONE** — `apply_recruitment_beats` in `process_result`: mission_victory /
   objective_kind / rep / act_reached conditions (catch-up semantics: a m6 win
   signs everyone whose mission threshold has passed). Joins surface in the
   debrief changed-lines, bead storyTag `hero-joined`, report `heroJoins`, and
   the next briefing's `briefing.hero_joined` Ketha nod. Grath/Halq flip their
   existing world character sheets to player=True.
3. **DONE** — `ACT2_REWARD_TABLE` (m6 2×legshot, m7 2×legamph, m8 2×legbart,
   m9 2×leginc, m10 1×legkeres) grants into `roster.cadre` on full-success
   act-2 missions, ledgered in `roster.grants`; each granted unit raises the
   cadre cap (clamped +8) so specials never squeeze the T1 vets.

## Wave 3 — Act texture — **BUILT**

1. **DONE** — `warband` enemyMode for act 1 (compiler act block): thinned
   static rings, no fortify, ×1.5 patrols, plus two roving packs with
   PatrolSweep orders riding the primary enemy camp's team. Mission card gets
   a warband threat line.
2. **DONE** — act-1 objective matrix in `quest_generator_v1.py`
   (`ACT1_KIND_ROTATION`: raid → seize → gate → hold → strike, +0.9 score
   preference, falls back when the map lacks the kind).
3. **DONE** — finale dressing: `persistentBaseRehydrate` snapshots respawn as
   standing bases (player-bloc → team 0; matching-empire → primary enemy team;
   top-10 defs, per-def ≤6, ≤30/zone, ≤3 zones); merc foothold scales to
   ~1.05×enemyScale on finales; `availableAllies` defectors become a real
   allied camp; `briefing.finale.overthrow/sovereignty/spire_jump` pools.
4. **DONE** — campaign completion: act-3 full success sets
   `state.campaignComplete`, the debrief headline becomes a
   `debrief.campaign_complete` epilogue line, and the next intent is tagged
   `epilogue` (defeat keeps the retry loop unchanged).

## Standing constraints

- Everything remains UNCOMMITTED until the owner triggers commits.
- Gadget main chunk: 192/200 locals, `gadget:GameFrame` near the 60-upvalue
  cap — pack new state into existing tables, define cold helpers as globals.
- Two stale offscreen-balance tests were realigned to the v0.8.4 multi-rate
  clock in Drop 2; any future rate retune must touch those expectations.

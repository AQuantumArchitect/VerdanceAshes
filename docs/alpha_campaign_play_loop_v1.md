# Verdance Alpha Campaign Play Loop v1

This is the playable loop for the measured-to-abstract campaign engine.

## What Owns What

- `state/campaign_state.json` is the campaign truth (schema `verdance-campaign-state/1.0`).
- `outbox/next_mission_intent.json` is the next sortie request.
- `scripts/build_next_mission_v1.ps1` compiles that intent into a BAR-playable mission.
- `mod/VerdanceAshes.sdd` is the **BAR mutator** (game archive) holding the campaign
  gadget, widgets, and generated mission seeds. It is junction-installed into
  `data\games\VerdanceAshes.sdd` by `scripts/install_mod_archive.ps1` and loaded via
  `GameType=Verdance Ashes $VERSION` (depends on Beyond All Reason).
- BAR savegames are launch/resume artifacts, not the campaign database.

## Fast Path (one click)

1. Run `PLAY_SESSION_V1.bat` (or the **Play Session** button in `LAUNCH_VERDANCE_CONSOLE.bat`).
2. BAR launches into the next mission. Play it.
   - The objective HUD (top of screen) shows the target, kill count, and extraction prompt.
   - Win/loss is detected automatically: destroy the objective structures (or hold the
     objective zone), then return to the extraction zone. Losing your commander or your
     whole force is a defeat.
3. When the game ends, the session watcher extracts the result from the infolog,
   advances the campaign (idempotent), and builds the next mission.
4. You get a sound + "next-ready" status. Run Play Session again for the next sortie.

`outbox/play_session.status.json` shows the live session phase
(`building → in-game → extracting → build-next → next-ready`).

## Manual Path

The individual steps still exist as console buttons / scripts:
`BUILD_NEXT_MISSION_V1.bat`, `PLAY_NEXT_MISSION_V1.bat`, `Extract + Advance v1`
(`scripts/run_full_cycle_v1.ps1 -WriteState`), `CREATE_NEXT_MISSION_SAVE_V1.bat`.

## Debug commands (in-game)

Objectives are automatic. For emergencies: `/vastatus`, `/vawin`, `/vafail`,
`/vapartial`, `/vazones`, `/vahelp`. Cheat-gated test hook:
`/luarules vatest_killobjective` destroys all tracked objective targets.

## Result contract

The gadget emits `VA_RESULT_JSON_*` markers with a 4-part idempotency key
(`campaignId|missionId|missionNumber|status`), `elapsedMinutes`,
`extractionStatus` (`clean`/`contested`), `destroyedObjectiveIds`, and
`objectiveResults` — everything the story engine consumes.

## Verification

- `scripts/run_headless_smoke.ps1` — fast-win cycle through the mutator.
- `scripts/verify_objective_automation.ps1` — genuine objective detection
  (cheat-kills targets, expects the gadget's own victory path).
- `python -m unittest discover tests` — story engine unit tests.

## Story & Difficulty (v2)

- Mission titles, Ketha briefing lines, and outcome-keyed debrief lines are generated
  by the engine from `data/story/ketha_voice.json` (deterministic per campaign moment —
  edit that file to retune the voice, no code changes needed).
- A briefing card shows for the first 45 seconds in-game (Space dismisses); a debrief
  screen with Ketha's reaction and extraction quality shows at mission end.
- Enemy force size scales with `expectedEnemyScale` (zone memory) × the difficulty
  coefficient (q6_contested); at ≥1.4 the enemy base gains tier-2 defenses. Enemy
  patrols defend the target zone on presence objectives and pressure the midline on
  destruction objectives. Raptor nests scale with accumulated hazard pressure.
- `scripts/verify_campaign_arc.ps1 -Missions N` chains N missions headlessly
  (state snapshot/restore) and writes `reports/arc_verify.latest.json`.

## Force design (v3)

Camps are assembled from faction rings around an **objective centerpiece** —
only the centerpiece is objective-tagged, so destruction missions are surgical
strikes into a defended camp, not base-wipes:

| objective | centerpiece | camp |
|---|---|---|
| economy_disrupt | fusion + adv solars + converter farm + storage | Cortex synth works |
| strike_relay | targeting facility + adv radar + fusion | Cortex relay installation |
| destroy_key_structure | LRPC + fusion + fortification walls | Armada bastion wing |
| seize_lane / gate_control | none (zone hold) | pure garrison, no eco |
| hive_clear_or_bypass | raptor hives (the hive IS the objective team) | swarm + spore turrets |
| choose_target_then_extract | two rival camps (Armada post / Cortex works) on separate allyteams | raptor swarm between them |

Perimeter turrets/walls face the player's approach; patrols screen the camp on
destruction missions and hold the zone on presence missions. Enemy commanders
keep building, so camps develop organically over the mission. Missions 1–2 run
an onboarding ramp (0.7×/0.85×).

## Balance methodology

`scripts/run_headless_balance_test.ps1 -ScenarioPath data\scenarios\generated\next_mission_intent.playable.json -Variant alpha_player -PlayerControllers simple,barbarian_aggressive -SimFrames 21600 -TimeoutSeconds 2400`
runs the generated mission with AI in the player seat (team 0, full player kit
+ commander). Target band: BARb-aggressive gains advantage/clears by the
mission horizon while SimpleAI stalls. Caveat: BARb walks its commander into
combat, so commander-loss defeats in these probes are an AI artifact — check
`VA_OBJECTIVE_TARGET_DOWN` counts in the infolog for objective progress too.

## Current Alpha Limitations

- Deployment and extraction zones are often the same zone, so destroy-objectives
  effectively end shortly after the targets die if you still hold your base.
- Presence objectives (seize_lane, gate_control) use a fixed 30s hold.
- The generated mission uses a compact proxy layout: human Legion player, one
  SimpleAI enemy target force, optional RaptorsAI pressure on wild maps.
- Offscreen campaign simulation is active, but persistent base rehydration is
  still a seed-spawn approximation.

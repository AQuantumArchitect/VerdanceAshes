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

## Current Alpha Limitations

- Deployment and extraction zones are often the same zone, so destroy-objectives
  effectively end shortly after the targets die if you still hold your base.
- Presence objectives (seize_lane, gate_control) use a fixed 30s hold.
- The generated mission uses a compact proxy layout: human Legion player, one
  SimpleAI enemy target force, optional RaptorsAI pressure on wild maps.
- Offscreen campaign simulation is active, but persistent base rehydration is
  still a seed-spawn approximation.

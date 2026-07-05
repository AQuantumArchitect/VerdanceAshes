# Verdance Alpha Campaign Play Loop v1

This is the first playable loop for the measured-to-abstract campaign engine.

## What Owns What

- `state/campaign_state.json` is the campaign truth.
- `outbox/next_mission_intent.json` is the next sortie request.
- `scripts/build_next_mission_v1.ps1` compiles that intent into a BAR-playable mission.
- `outbox/va_current.lua` is the generated mission seed read by the BAR Lua gadget.
- BAR savegames are launch/resume artifacts, not the campaign database.

## Fast Path

1. Run `LAUNCH_VERDANCE_CONSOLE.bat`.
2. Click `Build Next Mission`.
3. Click `Play Next Mission`, or run `PLAY_NEXT_MISSION_V1.bat`.
4. In BAR, play the sortie.
5. Use `/vastart` if the mission status is not active.
6. Use `/varesult` when you are ready to export the result.
7. In the console, click `Extract + Advance v1`.
8. Build/play the next mission.

## Savegame Path

If direct launch is awkward, run `CREATE_NEXT_MISSION_SAVE_V1.bat` or click `Create Save`.

That generates a BAR save from the current mission seed. Load that save from BAR, play, then export with `/varesult`.

## Current Alpha Limitations

- Objective completion is still mostly manual/export-driven. Use `/vawin`, `/vapartial`, or `/vafail` if the in-game state is clear before objective automation catches up.
- Extraction zones are represented in the mission seed and result schema, but the Lua gadget does not yet enforce physical extraction.
- The generated mission uses a compact proxy layout: human Legion player, one SimpleAI enemy target, and optional RaptorsAI pressure on wild maps.
- Offscreen campaign simulation is active in the v1 story engine, but persistent base rehydration is still a seed-spawn approximation.

## Useful Files

- `outbox/next_mission_intent.json`
- `outbox/next_mission_build_manifest.json`
- `data/scenarios/generated/next_mission_intent.playable.json`
- `playable_runs/latest_playable_variant_manifest.json`
- `outbox/va_current.lua`

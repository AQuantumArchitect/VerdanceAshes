# Verdance Story Engine v1 Owner Brief

Last updated: 2026-07-04

Source handoff:

```text
C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\inbox\verdance_codex_handoff_v1
```

## Promotion Accepted

Codex is now acting as chief development bot for the local Verdance's Ashes BAR campaign prototype. The project has moved from a multi-layer speculative architecture into one practical local implementation loop:

```text
BAR match telemetry -> Verdance story engine -> campaign state -> next mission intent -> BAR scenario/test loop
```

The goal is not polish. The goal is a reliable machine that can run, observe, advance, and explain itself.

## Current Source-of-Truth Stack

Use these in this order:

1. Live BAR runtime facts: `UnitDefs`, map names, map dimensions, team/unit state, infolog output.
2. Workspace-tested data from headless BAR runs, especially the seven-map campaign AI baseline export.
3. v1 contracts in `inbox/verdance_codex_handoff_v1/contracts/INTERFACE_CONTRACTS.md`.
4. v1 schemas in `inbox/verdance_codex_handoff_v1/schemas/`.
5. v1 seed data in `inbox/verdance_codex_handoff_v1/data/`.
6. Older v0.5 state and Lua files as lineage only.
7. React/HTML prototypes as design references only, not implementation targets.

## Important Architectural Change

Older memory said the BAR interface layer should not be the campaign brain. The v1 handoff changes that operating posture: the translator, BAR interface, and first story engine should be flattened into one local development effort.

This does not mean Lua should become a giant campaign system. Practical split:

- Lua/BAR side: gather live facts, expose commands, emit telemetry/result markers.
- Workspace scripts: extract JSON, validate schemas, advance campaign state, write next mission intent/story events.
- Campaign logic: stay idempotent, file-based, inspectable, and easy to test headlessly.

## Required Runtime Contracts

Telemetry output:

```text
outbox\bar_zone_telemetry.latest.json
schemaVersion = bar-zone-telemetry/1.0
```

Terminal match result input:

```text
inbox\latest_va_result.json
schemaVersion = verdance-match-result/1.0
```

Campaign state:

```text
state\campaign_state.json
schemaVersion = verdance-campaign-state/1.0
```

Next mission intent:

```text
outbox\next_mission_intent.json
schemaVersion = verdance-mission-intent/1.0
```

Story events:

```text
outbox\story_events.latest.json
schemaVersion = verdance-story-events/1.0
```

Idempotency key:

```text
campaignId|missionId|missionNumber|status
```

If this key has already been processed, campaign advancement must not mutate state again.

## Required BAR Commands

The command layer must support:

```text
/vahelp
/vaping
/varules
/vastatus
/vaexport
/vaadvance
/varesult
```

Expected diagnostic markers:

```text
VA_PING_WIDGET_OK
VA_PING_RULES_OK
VA_EXPORT_OK
VA_ADVANCE_OK
VA_RESULT_JSON_COMPACT
```

## Data Model Summary

The v1 campaign state tracks:

- `campaignId`
- `missionNumber`
- `currentMissionId`
- `pathSignal`
- graph scalars
- reputation
- companion state
- `history`
- `processedResults`

Core graph scalars:

- `q0_armada_cortex`: lower Armada, higher Cortex.
- `q2_void_structure`: Void influence / volatility.
- `q6_contested`: line-world instability.
- `q6_independent`: Ashwalker/free-space sovereignty.
- `q7_resource_scarcity`: economic pressure.
- `pathSignalA/B/C`: accumulated campaign orientation.

Every terminal match appends one history bead to `history`.

## Story Layer

Ketha is the v1 companion voice. Dialogue should be short, reactive, and emitted as structured data first.

Event kinds:

- `dialogue`
- `graph_delta`
- `companion_delta`
- `reputation_delta`
- `unlock`
- `warning`
- `mission_hook`

Current useful seed line:

```text
The clans are listening. That matters more than the map says.
```

## Map and Zone Notes

The handoff's `all_that_simmers.zone_map.json` is a starter placeholder. It must not override our newer tested authored zones.

Canonical seven-map pool:

- `all_that_simmers`
- `koom_valley`
- `tabula`
- `ancient_bastion`
- `the_rock_jungle`
- `eye_of_horus`
- `greenest_fields`

Note: the handoff uses `rock_jungle` in one catalog entry, but the tested workspace uses `the_rock_jungle`. Prefer `the_rock_jungle` internally and add alias support if needed.

Current alpha campaign interpretation from testing:

1. Greenest Fields: build/economy onboarding.
2. Eye of Horus: strike/pocket-control confidence mission.
3. Koom Valley: expand/tempo lane.
4. Tabula: maneuver/recover through plateau gates.
5. Ancient Bastion: siege.
6. The Rock Jungle: survive wilds.
7. All That Simmers: choose under full faction/wild pressure.

## What Supersedes What

Superseded:

- Old five-zone All That Simmers placeholder names as final telemetry zones.
- v0.5 state schema as active state format.
- React/HTML prototypes as implementation path.
- Single global density normalization for all map families.

Preserved:

- v0.5 history as lineage.
- Ketha/Rhekk concept and companion continuity.
- Graph-as-history premise.
- Path A/B/C structure.
- File-based JSON contracts.
- BAR-AI headless testing as calibration source.

## Next Implementation Sequence

Current v1 implementation entrypoints:

- `tools\verdance_story_engine_v1.py`: measured-to-abstract campaign loop.
- `scripts\advance_campaign_v1.ps1`: Windows wrapper for v1 advancement.
- `scripts\run_full_cycle_v1.ps1`: extract latest result/telemetry, then run v1 advancement.
- `scripts\build_next_mission_v1.ps1`: compiles the current v1 mission intent into a playable BAR scenario, seed, and startscript.
- `BUILD_NEXT_MISSION_V1.bat`: compiles the next mission without launching BAR.
- `PLAY_NEXT_MISSION_V1.bat`: compiles and launches the next mission in visible BAR.
- `CREATE_NEXT_MISSION_SAVE_V1.bat`: compiles the next mission and creates a BAR savegame artifact.
- `outbox\next_mission_intent.json`: latest materialized v1 deployment intent.
- `outbox\next_mission_build_manifest.json`: latest compiled playable mission summary.
- `outbox\story_events.latest.json`: latest structured story events.
- `docs\alpha_campaign_play_loop_v1.md`: current human playtest loop.

1. Environment health check:
   - locate active `BAR.sdd`;
   - locate active `infolog.txt`;
   - confirm LuaUI/LuaRules load paths;
   - confirm headless runner still works after sleep/restart cycles.

2. Normalize state:
   - migrate or seed `state\campaign_state.json` to `verdance-campaign-state/1.0`;
   - preserve old v0.5 state as backup;
   - add processed-result ledger.

3. Build local advancement tool:
   - promote `tools\verdance_story_engine.py` into workspace scripts or adapt current PowerShell/Python tooling;
   - validate match result;
   - advance state exactly once;
   - write `next_mission_intent.json`;
   - write `story_events.latest.json`.

4. Repair BAR command loop:
   - `/vaping`;
   - `/varules`;
   - `/vahelp`;
   - `/vastatus`;
   - `/vaexport`;
   - `/varesult`;
   - `/vaadvance`.

5. Connect telemetry to story:
   - derive terminal `latest_va_result.json` from telemetry/headless result;
   - run advancement;
   - confirm duplicate result is skipped.

6. Run acceptance checklist:
   - successful telemetry JSON;
   - before/after campaign state JSON;
   - next mission intent;
   - story events;
   - ledger proof;
   - infolog excerpts.

## Immediate Risks

- The existing `state\campaign_state.json` is v0.5, not v1.
- The handoff's All That Simmers zones are placeholders and conflict with tested authored zones.
- Some long-run headless artifacts were mixed by interrupted/resumed runs; export tooling now filters map/zone mismatches, but future runners should prevent this at source.
- `SimpleAI` versus `SimpleDefenderAI` shortName must keep being verified against actual BAR runtime support.
- Direct BAR file writes may fail under install permissions; infolog marker extraction remains the most reliable transport.

## Working Rule

Every new feature should answer one of these questions with a file or marker:

1. What happened in BAR?
2. What did that mean for the campaign graph?
3. What mission should BAR run next?
4. Can we prove processing the same result twice is harmless?

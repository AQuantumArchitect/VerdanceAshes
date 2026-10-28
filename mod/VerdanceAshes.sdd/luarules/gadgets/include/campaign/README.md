# The campaign gadget, in parts

`game_verdance_campaign.lua` (one level up) is the core. It holds the engine call-ins and sets the
order these parts load in.

## How the parts share
- **One environment.** Each part runs in that gadget's environment (`VFS.Include(path, gadget)`, the
  same way BAR's own `include()` works). So the parts share globals with each other and with the
  core, and with nothing else.
- **Locals stay private.** Anything a part declares `local` is invisible to the other parts.
- **The header says what is shared.** Each part's header lists what it **Provides** (globals another
  part or the core reads) and which parts it **Uses**.
- **Short call-ins.** The core's call-ins are lists of named steps. A step that lives in a part says
  so: `-- Called by gadget:GameFrame.`

## Where to start reading
- **The core, top to bottom.** `gadget:Initialize` sets the sortie up. `gadget:GameStart` places
  everyone. `gadget:GameFrame` is the list of what ticks each frame. The Unit*/Feature* call-ins say
  who reacts to what.
- **One part per area.** Every part's first line says what it is (the table below).

| Part | What it is |
|---|---|
| `unsynced.lua` | the unsynced half: forwards the synced events to LuaUI and holds the start pause |
| `state.lua` | the sortie itself (mission, zone map, status, teams), the marks registry and the JSON helpers |
| `result.lua` | the sortie result: resultJson writes the result_* sections in order (RESULT_SECTIONS); chunked logging, logResult, the headless finish |
| `result_heroes.lua` | the result's hero parts: hero states and outcomes, who was recruited, the named dead and wounded, companions |
| `result_world.lua` | the result's world parts: the zone graph, reputation, the economy, beliefs and kings |
| `result_objective.lua` | the result's objective parts: how it completed, targets destroyed, secondaries, surviving installs, shell scars |
| `result_company.lua` | the result's company parts: what of ours is on the field, survivors and their XP, loan units, metal and Tenebrium |
| `mission_data.lua` | reading the mission seed and the zone map |
| `units.lua` | unit-def helpers and metal spots |
| `mentors.lua` | pack mentors (Spoke, the leads): subordinate XP and field effects |
| `hero_spawn.lua` | a hero's unit on the field: modifiers, tags, registration, auras |
| `spawn.lua` | placing units: dry landing, standable ground, spawnOneUnit / spawnUnitSpec |
| `crew.lua` | the company on the field: the roster, who drops (crew confirm, the hot drop), anchor keeps, what was dropped |
| `crew_storage.lua` | the company's metal and energy storage caps, re-applied after BAR's own start reset |
| `crew_packs.lua` | a hero's pack on the field (VA_CREW_spawnHeroPack) and the bonds between heroes who drop together |
| `field_recruits.lua` | wild heroes: recruit wrecks, field factories, unit printers |
| `setup.lua` | the playable setup: camps, forces and the player's start |
| `telemetry.lua` | zone cells, per-zone metrics, dev telemetry and the headless/profiling options |
| `waterline.lua` | the waterline (hydrology) and zone flow |
| `translation.lua` | the translation matrix packet |
| `objectives.lua` | the objective: its kinds and modes, its state (targets, completion, capture), the target zone |
| `objective_pad.lua` | the pad: the one zone the company lands and lifts from |
| `objective_checks.lua` | the periodic checks and completion: onObjectiveComplete, all marks done, purge, wipe, the soft clock |
| `objective_targets.lua` | what the objective's targets are: the living shell's eco and teeth, high-value marks, and a target going down |
| `objective_presence.lua` | holding ground: the capture pocket and regrow pressure, presence and fortify checks, claim strength |
| `reinforcements.lua` | enemy response waves and where they enter |
| `heroes.lua` | the named heroes: their table, the down marks, lost and recovered, the rescue contract, end-of-sortie states |
| `hero_wrecks.lua` | a hero's wreck: death to wreck, the rez that brings them back, a wreck that is destroyed or times out |
| `hero_joins.lua` | a wild hero joins: raised, captured or a field factory taken; recruited ids kept across reloads |
| `beats.lua` | in-mission beats (authored triggers) |
| `terminal.lua` | ending the sortie: the terminal crunch and the GG entry points |
| `start.lua` | start of the sortie: doctrine, commanders, perks, start resources, Tenebrium |
| `logistics.lua` | mercenary logistics: the deploy kit, pending deliveries, the brute crash |
| `devcmd.lua` | the /luarules va* playtest commands, the headless start and debug auto-progress |

Load order is the order of the core's `VFS.Include` lines (above, after `unsynced`). Only code
that runs at load time cares about it. Each part declares its own state at its top, and no part
reads another part's state at load.

## Keeping it honest
- `python3 tools/campaign_parts.py` checks two things:
  - every global a part reads is defined by some part. This catches a part calling a `local` of
    another part, which Lua would otherwise only report when that line runs.
  - every header still matches the code.
- `python3 tools/campaign_parts.py --fix` rewrites the headers.
- `tests/test_campaign_parts.py` runs the same checks.
- Tests and harnesses that read the gadget's source use `tools/campaign_lua.py` (`source()`), not
  the core file alone.
- `tests/test_campaign_local_budget_v1.py` keeps each part under Lua 5.1's 200-local limit.

## The sortie result
`resultJson` (in `result.lua`) builds one context (`resultContext`) and then runs the sections in
`RESULT_SECTIONS` order. Each section is a `result*Fields(c)` function in the part that knows its
facts: sortie, objective, capture, company, heroes, metal, Tenebrium, world. Python reads these
keys (`verdance.hub.contract`). `tests/test_result_contract.py` lists every section's keys in
order, so adding, dropping or moving a key is a change you make there on purpose.

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
| `result.lua` | the sortie result: every JSON part, chunked logging, the headless finish |
| `mission_data.lua` | reading the mission seed and the zone map |
| `units.lua` | unit-def helpers and metal spots |
| `mentors.lua` | pack mentors (Spoke, the leads): subordinate XP and field effects |
| `hero_spawn.lua` | a hero's unit on the field: modifiers, tags, registration, auras |
| `spawn.lua` | placing units: dry landing, standable ground, spawnOneUnit / spawnUnitSpec |
| `crew.lua` | the company on the field: roster, hero packs, bonds, crew confirm, the hot drop |
| `field_recruits.lua` | wild heroes: recruit wrecks, field factories, unit printers |
| `setup.lua` | the playable setup: camps, forces and the player's start |
| `telemetry.lua` | zone cells, per-zone metrics, dev telemetry and the headless/profiling options |
| `waterline.lua` | the waterline (hydrology) and zone flow |
| `translation.lua` | the translation matrix packet |
| `objectives.lua` | the objective: kind and mode, the pad, living-shell claims, presence / fortify / wipe / soft clock |
| `reinforcements.lua` | enemy response waves and where they enter |
| `heroes.lua` | hero lifecycle: down, wreck, rez, lost, recovered, field joins |
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

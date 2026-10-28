# The campaign gadget, in parts

`game_verdance_campaign.lua` (one level up) is the core: the engine call-ins and the order these
parts load in. Each part runs in that gadget's environment (`VFS.Include(path, gadget)`), so the
parts share globals with each other and with the core, and nothing else. A part's header lists
what it shares; everything else in it is `local`.

Tests and harnesses read the whole gadget through `tools/campaign_lua.py` (`source()`), not the
core file alone.

| Part | What it is |
|---|---|
| `unsynced.lua` | the unsynced half: forwards the synced events to LuaUI and holds the start pause |
| `state.lua` | the sortie itself (mission, zone map, status, teams), the marks registry and the JSON helpers |
| `result.lua` | the sortie result: every JSON part, chunked logging, the headless finish |
| `mission_data.lua` | reading the mission seed and the zone map |
| `units.lua` | unit-def helpers and metal spots |
| `mentors.lua` | pack mentors (Spoke, the leads): subordinate XP and field effects |
| `hero_spawn.lua` | a hero's unit on the field: modifiers, tags, registration |
| `spawn.lua` | placing units: dry landing, standable ground, spawnOneUnit / spawnUnitSpec |
| `crew.lua` | the company on the field: roster, hero packs, bonds, crew confirm, the hot drop |
| `field_recruits.lua` | wild heroes: recruit wrecks, field factories, who waits where |
| `setup.lua` | the playable setup: camps, forces and the player's start |
| `telemetry.lua` | zone cells, per-zone metrics and dev telemetry |
| `waterline.lua` | the waterline (hydrology) and zone flow |
| `translation.lua` | the translation matrix packet |
| `objectives.lua` | the objective: kind and mode, the pad, living-shell claims, presence / fortify / wipe / soft clock |
| `reinforcements.lua` | enemy response waves and where they enter |
| `heroes.lua` | hero lifecycle: down, wreck, rez, lost, recovered, field joins |
| `beats.lua` | in-mission beats (authored triggers) |
| `terminal.lua` | ending the sortie: the terminal crunch and the GG entry points |
| `start.lua` | start of the sortie: commanders, perks, start resources, Tenebrium handlers |
| `logistics.lua` | mercenary logistics: the deploy kit, pending deliveries, the brute crash |
| `devcmd.lua` | the /luarules va* playtest commands |

Load order is the order above (the core's `VFS.Include` lines). Only load-time code cares:
`state.lua` declares the shared state first, and a part that builds a table at load reads only
what loaded before it.

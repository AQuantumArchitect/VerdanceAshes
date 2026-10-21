# BAR Zone Telemetry Exporter v1 Plan

## Output Contract

Primary deliverable:

```text
C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\outbox\bar_zone_telemetry.latest.json
```

Required top-level shape:

```json
{
  "schemaVersion": "bar-zone-telemetry/1.0",
  "exportId": "string",
  "matchId": "string",
  "map": {
    "name": "string",
    "mapId": "string",
    "size": { "x": 0, "z": 0 }
  },
  "frame": 0,
  "seconds": 0,
  "terminal": {
    "isTerminal": false,
    "status": "active",
    "winnerAllyTeamId": null
  },
  "teams": [],
  "zones": {}
}
```

Allowed terminal statuses: `active`, `victory`, `defeat`, `draw`, `unknown`.

## Target Map

First target:

```text
All That Simmers
```

Normalized map ID:

```text
all_that_simmers
```

Current runtime smoke observed:

```text
map.name = All That Simmers v1.1.1
map.size.x = 7168
map.size.z = 10240
```

## Required Zones

The authored workspace zone map lives at:

```text
data/zone_maps/all_that_simmers.zone_map.json
```

It is staged into BAR VFS as:

```text
BAR.sdd/singleplayer/verdance_ashes/generated/zone_map_current.lua
```

Required zone IDs and labels:

- `ATS_CENTER`: Armada Center Hold
- `ATS_WEST_FORWARD`: Ashwalker West Forward Base
- `ATS_EAST_FORWARD`: Ashwalker East Forward Base
- `ATS_NORTH_APPROACH`: Northern Canopy Approach
- `ATS_SOUTH_APPROACH`: Southern Swamp Approach

Rectangles are sufficient for v1.

## Team Telemetry

Each team entry must include:

- `teamId`
- `allyTeamId`
- `side`
- `isDead`
- `isAi`
- `metrics`
- `unitCountsByDef`

Required team metrics:

- `armyValue`
- `buildPower`
- `defensiveValue`
- `totalUnitValue`
- `metalIncome`
- `energyIncome`

## Zone Telemetry

Each `zones.<zoneId>` entry must include:

- `zoneId`
- `label`
- `teams`

Each zone-team entry must include:

- `teamId`
- `allyTeamId`
- `side`
- `metrics`
- `unitCountsByDef`

Required zone-team metrics:

- `armyValue`
- `buildPower`
- `defensiveValue`
- `totalUnitValue`
- `unitCount`
- `combatUnitCount`
- `builderUnitCount`
- `structureCount`

## Metric Definitions

Use existing BAR/caster-style APIs if stable and accessible. If not, compute from live units and runtime `UnitDefs`.

Initial acceptable approximations:

- `armyValue`: metal value of mobile combat units
- `buildPower`: sum of constructor, builder, and nano build power
- `defensiveValue`: metal value of static defenses
- `totalUnitValue`: metal value of all active non-debris units and structures
- `metalIncome`: current team metal income
- `energyIncome`: current team energy income

Unit keys must be BAR runtime unitDef names, such as `armpw`, `armwar`, `armck`, `armllt`, `corgator`, `corcon`, `corthug`, `legcom`.

## Commands

Required commands:

- `/vahelp`: print available commands
- `/vaping`: print `VA_PING_WIDGET_OK`
- `/varules`: print `VA_PING_RULES_OK`
- `/vaexport`: export telemetry and print `VA_EXPORT_OK` or `VA_EXPORT_ERROR`

For headless tests, the command path can be driven through BAR `debugcommands`, as already proven by `scripts/run_headless_smoke.ps1`.

## Transport

Preferred final state:

1. BAR Lua emits telemetry via direct write if safe.
2. Otherwise BAR Lua emits compact or chunked JSON into `infolog.txt`.
3. Workspace script extracts into `outbox/bar_zone_telemetry.latest.json`.

Current proven transport is infolog marker extraction.

Preferred markers:

```text
VA_TELEMETRY_JSON_BEGIN
VA_TELEMETRY_JSON_CHUNK 1/3 <payload>
VA_TELEMETRY_JSON_END
```

Fallback compact marker:

```text
VA_TELEMETRY_JSON_COMPACT { ... }
```

## Test Ladder

1. Lua load: no BAR Lua syntax/runtime errors in `infolog.txt`.
2. Ping widget: `/vaping` yields `VA_PING_WIDGET_OK`.
3. Ping rules: `/varules` yields `VA_PING_RULES_OK`.
4. Export command: `/vaexport` yields `VA_EXPORT_OK`.
5. JSON file exists at `outbox/bar_zone_telemetry.latest.json`.
6. JSON parses and has required top-level fields.
7. `map.mapId == "all_that_simmers"`.
8. All five zones are present.
9. At least one team has non-empty `unitCountsByDef` when live units exist.
10. At least one zone has a team with `metrics.unitCount > 0` when units are inside zones.

## Likely Next Implementation Move

Extend the existing LuaRules Verdance campaign gadget or add a sibling gadget that:

- scans `Spring.GetTeamList()` and `Spring.GetTeamInfo()`
- scans live units via `Spring.GetAllUnits()` or team-scoped unit calls
- maps each unit to a zone using `Spring.GetUnitPosition()` and zone bounds
- classifies units from `UnitDefs[unitDefID]`
- builds the `bar-zone-telemetry/1.0` JSON
- emits `VA_TELEMETRY_JSON_*` markers

Then add a workspace extractor/validator script that writes:

```text
outbox/bar_zone_telemetry.latest.json
```

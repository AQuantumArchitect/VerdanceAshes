# Codex Task Spec: BAR Zone Telemetry Exporter v1

## Objective

Build a working Beyond All Reason interface layer that exports live or headless match telemetry into a valid JSON file for upstream tactical processing.

The deliverable is a local BAR integration that produces:

```text id="78wgpw"
bar_zone_telemetry.latest.json
```

from a BAR match.

This is the v1 product. Do not build campaign graph logic, mission generation, replay mining, or polished dashboards yet.

---

# 1. Required output file

Produce this file:

```text id="ppho4e"
Documents/BAR_Verdance_Workspace/outbox/bar_zone_telemetry.latest.json
```

The file must contain valid JSON.

It must be parseable by standard JSON parsers.

It must be overwritten or refreshed on each successful export.

---

# 2. Required JSON schema

The output must follow this shape:

```json id="6j6b2t"
{
  "schemaVersion": "bar-zone-telemetry/1.0",
  "exportId": "string",
  "matchId": "string",
  "map": {
    "name": "string",
    "mapId": "string",
    "size": {
      "x": 0,
      "z": 0
    }
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

## Required top-level fields

```text id="286omn"
schemaVersion
exportId
matchId
map
frame
seconds
terminal
teams
zones
```

## Required `map` fields

```text id="5y5zgu"
map.name
map.mapId
map.size.x
map.size.z
```

## Required `terminal` fields

```text id="jqrx88"
terminal.isTerminal
terminal.status
terminal.winnerAllyTeamId
```

Allowed `terminal.status` values:

```text id="l44umc"
active
victory
defeat
draw
unknown
```

---

# 3. Required team telemetry

Each team entry must have this shape:

```json id="0wjlgy"
{
  "teamId": 0,
  "allyTeamId": 0,
  "side": "armada",
  "isDead": false,
  "isAi": false,
  "metrics": {
    "armyValue": 0,
    "buildPower": 0,
    "defensiveValue": 0,
    "totalUnitValue": 0,
    "metalIncome": 0,
    "energyIncome": 0
  },
  "unitCountsByDef": {
    "armpw": 12,
    "armwar": 4
  }
}
```

## Required team fields

```text id="syj1t4"
teamId
allyTeamId
side
isDead
isAi
metrics
unitCountsByDef
```

## Required team metrics

```text id="rdmkgn"
armyValue
buildPower
defensiveValue
totalUnitValue
metalIncome
energyIncome
```

All metric values must be numbers.

`unitCountsByDef` must use BAR unit definition names as keys.

Examples:

```text id="npwmim"
armpw
armwar
armck
armllt
corgator
corcon
corthug
legcom
```

Do not invent or translate unit IDs. Use BAR runtime unitDef names.

---

# 4. Required zone telemetry

The output JSON must include zone-level telemetry under `zones`.

Each zone must have this shape:

```json id="kfwvy4"
{
  "ATS_CENTER": {
    "zoneId": "ATS_CENTER",
    "label": "Armada Center Hold",
    "teams": {
      "0": {
        "teamId": 0,
        "allyTeamId": 0,
        "side": "armada",
        "metrics": {
          "armyValue": 0,
          "buildPower": 0,
          "defensiveValue": 0,
          "totalUnitValue": 0,
          "unitCount": 0,
          "combatUnitCount": 0,
          "builderUnitCount": 0,
          "structureCount": 0
        },
        "unitCountsByDef": {
          "armpw": 4
        }
      }
    }
  }
}
```

## Required zone fields

```text id="2mdb6a"
zoneId
label
teams
```

## Required zone-team fields

```text id="fa9c2e"
teamId
allyTeamId
side
metrics
unitCountsByDef
```

## Required zone-team metrics

```text id="pvz1k1"
armyValue
buildPower
defensiveValue
totalUnitValue
unitCount
combatUnitCount
builderUnitCount
structureCount
```

---

# 5. First target map

Implement first against:

```text id="m0gm1j"
All That Simmers
```

Use this map ID:

```text id="beu1kz"
all_that_simmers
```

If the runtime BAR map name differs, normalize it to this `mapId` in the output while preserving the actual map name in `map.name`.

---

# 6. Required initial zones

Create and load a zone map for All That Simmers with these zones:

```text id="l80qcn"
ATS_CENTER
ATS_WEST_FORWARD
ATS_EAST_FORWARD
ATS_NORTH_APPROACH
ATS_SOUTH_APPROACH
```

## Required zone labels

```text id="vqvbrx"
ATS_CENTER: Armada Center Hold
ATS_WEST_FORWARD: Ashwalker West Forward Base
ATS_EAST_FORWARD: Ashwalker East Forward Base
ATS_NORTH_APPROACH: Northern Canopy Approach
ATS_SOUTH_APPROACH: Southern Swamp Approach
```

## Required zone-map file

Create one of the following, whichever is more practical:

Preferred workspace JSON:

```text id="8ou208"
Documents/BAR_Verdance_Workspace/data/zone_maps/all_that_simmers.zone_map.json
```

or BAR Lua version:

```text id="mwpi0h"
BAR.sdd/singleplayer/verdance_ashes/generated/zone_map_current.lua
```

## Required zone-map schema

For JSON:

```json id="stz2em"
{
  "schemaVersion": "verdance-zone-map/1.0",
  "mapId": "all_that_simmers",
  "mapName": "All That Simmers",
  "coordinateSystem": "elmos",
  "zones": [
    {
      "zoneId": "ATS_CENTER",
      "label": "Armada Center Hold",
      "shape": "rect",
      "bounds": {
        "xMin": 0,
        "xMax": 0,
        "zMin": 0,
        "zMax": 0
      }
    }
  ]
}
```

Use rectangles first. Exact coordinates may be rough in the first pass, but they must be valid within the actual map dimensions.

---

# 7. Metric definitions

Use existing BAR/caster-style metrics if there is a stable accessible source.

If not, compute directly from live units and runtime `UnitDefs`.

Minimum definitions:

```text id="kjlqm7"
armyValue:
  metal value of mobile combat units

buildPower:
  sum of constructor / builder / nano build power

defensiveValue:
  metal value of static defenses

totalUnitValue:
  metal value of all active non-debris units and structures

metalIncome:
  current team metal income

energyIncome:
  current team energy income
```

For v1, approximate classification is acceptable as long as it is consistent and documented.

---

# 8. Unit source of truth

Use BAR runtime `UnitDefs` as the source of truth.

Do not hardcode the React prototype unit database as canonical truth.

The React prototypes are mock/intermediary UI concepts only.

The telemetry output should pass unit definition names through unchanged.

---

# 9. BAR integration files

Create or repair these files as needed:

```text id="493qpt"
BAR.sdd/luaui/Widgets/gui_verdance_bar_exporter.lua
BAR.sdd/luarules/gadgets/game_verdance_bar_bridge.lua
```

The exact internal architecture is flexible.

The required external behavior is not flexible.

---

# 10. Required in-game commands

Implement these slash commands:

```text id="x89sqt"
/vahelp
/vaping
/varules
/vaexport
```

## `/vahelp`

Print available Verdance commands.

## `/vaping`

Print a clear confirmation that the LuaUI widget is loaded.

Required output substring:

```text id="y6g0fs"
VA_PING_WIDGET_OK
```

## `/varules`

Print a clear confirmation that the LuaRules gadget is loaded or reachable.

Required output substring:

```text id="xupy61"
VA_PING_RULES_OK
```

## `/vaexport`

Generate/export `bar_zone_telemetry.latest.json`.

Required output substring on success:

```text id="05ucqa"
VA_EXPORT_OK
```

Required output substring on failure:

```text id="1kbpgd"
VA_EXPORT_ERROR
```

---

# 11. Export transport

Preferred export path:

```text id="s1y7kv"
Documents/BAR_Verdance_Workspace/outbox/bar_zone_telemetry.latest.json
```

If direct file write is blocked or unreliable, use this fallback:

```text id="ra1pd5"
Emit JSON to infolog.txt using markers.
Codex extracts it into the required output file.
```

Preferred infolog markers:

```text id="qevo1o"
VA_TELEMETRY_JSON_BEGIN
VA_TELEMETRY_JSON_CHUNK 1/3 <payload>
VA_TELEMETRY_JSON_CHUNK 2/3 <payload>
VA_TELEMETRY_JSON_CHUNK 3/3 <payload>
VA_TELEMETRY_JSON_END
```

Fallback single-line marker:

```text id="dc31ge"
VA_TELEMETRY_JSON_COMPACT { ... }
```

The final result must still be the output file:

```text id="l0e4l5"
bar_zone_telemetry.latest.json
```

---

# 12. Headless testing requirements

Create a repeatable test command or script that Codex can run locally.

Minimum test script responsibilities:

```text id="cbqdh1"
1. Start or attach to a BAR test/headless instance if possible.
2. Confirm LuaUI widget loaded or report why not.
3. Confirm LuaRules gadget loaded or report why not.
4. Run or simulate `/vaexport`.
5. Validate that bar_zone_telemetry.latest.json exists.
6. Parse the JSON.
7. Validate required fields.
8. Print PASS/FAIL summary.
```

If full headless BAR automation is hard, create the closest possible staged tests:

```text id="pcy09t"
- static Lua syntax check
- local JSON schema validation
- infolog extraction test from sample log
- live manual command test
```

---

# 13. Acceptance tests

The task is not complete until these pass.

## Test A — LuaUI ping

Command:

```text id="hr2lhv"
/vaping
```

Pass condition:

```text id="bgw4q0"
In-game console or infolog contains VA_PING_WIDGET_OK
```

## Test B — LuaRules ping

Command:

```text id="bmnvih"
/varules
```

Pass condition:

```text id="cwr4gm"
In-game console or infolog contains VA_PING_RULES_OK
```

## Test C — export command

Command:

```text id="lnw5ks"
/vaexport
```

Pass condition:

```text id="vdsyqr"
VA_EXPORT_OK appears
bar_zone_telemetry.latest.json exists
JSON parses successfully
```

## Test D — top-level schema

Pass condition:

```text id="e5k0nb"
schemaVersion == "bar-zone-telemetry/1.0"
map exists
teams exists
zones exists
```

## Test E — map target

Pass condition:

```text id="fhj33c"
For All That Simmers:
map.mapId == "all_that_simmers"
```

## Test F — zones loaded

Pass condition:

```text id="mhrgwg"
zones contains:
ATS_CENTER
ATS_WEST_FORWARD
ATS_EAST_FORWARD
ATS_NORTH_APPROACH
ATS_SOUTH_APPROACH
```

## Test G — unit counts

Pass condition:

```text id="r1w8ue"
At least one team has non-empty unitCountsByDef when live units exist.
```

## Test H — zone assignment

Pass condition:

```text id="r3vqvj"
At least one zone has a team entry with unitCount > 0 when units are present inside a zone.
```

---

# 14. Deliverables

Return the following to the supervising ChatGPT thread:

```text id="ed8z91"
1. Paths of files created/modified.
2. Exact commands/scripts used to test.
3. PASS/FAIL result for each acceptance test.
4. Contents of one successful bar_zone_telemetry.latest.json.
5. Relevant infolog excerpts for /vaping, /varules, and /vaexport.
6. Any known limitations or fragile assumptions.
```

---

# 15. Non-goals for this task

Do not spend time on:

```text id="tr5smt"
campaign graph mutation
mission selection
mission seed generation
scenario menu integration
replay archive ingestion
hydrology gameplay effects
polished HTML dashboard
full unit lore taxonomy
React UI implementation
```

Those are later tasks.

This v1 is only the BAR telemetry exporter.

---

# 16. Definition of done

This task is done when a BAR/headless test produces a valid:

```text id="qew87o"
Documents/BAR_Verdance_Workspace/outbox/bar_zone_telemetry.latest.json
```

for All That Simmers, containing:

```text id="fvyxnu"
map identity
team telemetry
unitCountsByDef
five named zones
zone-level telemetry
valid JSON
```

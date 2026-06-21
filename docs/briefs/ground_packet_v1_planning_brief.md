# Codex Ground Packet: Verdance BAR Interface Layer v1 Planning Brief

## Situation

We now have three layers:

```text
Campaign Overmind
  ↓
Tactical / Map Comprehension Intermediary
  ↓
BAR Interface Layer
  ↓
Beyond All Reason
```

You, Codex, are responsible for the BAR Interface Layer on the local Windows machine.

This layer should connect tactical/campaign intent to BAR and export BAR telemetry back upward.

Do not treat the current React prototypes as executable specifications. Treat them as design intent.

## What the intermediary documents are

There are two upstream prototype documents.

### 1. Tactical Map Comprehension Matrix

This prototype contains:

```text
- hardcoded faction/unit database
- hardcoded map list
- per-map quadrant definitions
- water/hydrology simulation
- local density/coherence matrix
- simulated unit populations per quadrant
- mock ingress JSON
```

Its purpose is to imagine how tactical control and map-state comprehension might look.

It is not authoritative for BAR unit stats.

Important implication:

```text
The intermediary wants per-map, per-zone facts:
- unit counts
- army value
- build power
- defense value
- economy indicators
- environmental/hydrology hints where relevant
```

### 2. Campaign Overmind Interface

This prototype contains:

```text
- outbound campaign packet generator
- hydrology qubit / environment settings
- faction AV budgets
- quest directive selector
- deterministic chaotic spawn seeding
- mock inbound tactical summary
```

Its purpose is to imagine bidirectional flow:

```text
Campaign Overmind → BAR mission intent
BAR telemetry → Tactical summary → Campaign Overmind
```

Important implication:

```text
The upstream system wants to send mission intent downward and receive tactical telemetry upward.
```

## What Codex should build first

Build the BAR-facing sensor/export layer first.

Do not build the full campaign loop yet.

Do not build scenario-menu integration yet.

Do not build replay mining yet.

Do not build hydrology simulation yet.

First target:

```text
BAR match → zone telemetry JSON
```

## Primary deliverable

Produce a stable, parseable file:

```text
bar_zone_telemetry.latest.json
```

This file should represent the current or completed BAR match.

Minimum useful fields:

```json
{
  "schemaVersion": "bar-zone-telemetry/1.0",
  "exportId": "local-debug-export-001",
  "matchId": "local-debug-match-001",
  "map": {
    "name": "All That Simmers",
    "mapId": "all_that_simmers",
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

## First map target

Start with:

```text
All That Simmers
```

Reason:

```text
- user selected it as first target
- simpler than hydrology-heavy campaign maps
- useful layout: Armada center zone plus Ashwalker side/forward zones
- good test map for zone telemetry
```

## Initial zone model

Create a zone-map file for All That Simmers.

File target:

```text
singleplayer/verdance_ashes/generated/zone_map_current.lua
```

or, if easier for Codex tooling:

```text
Documents/BAR_Verdance_Workspace/data/zone_maps/all_that_simmers.zone_map.json
```

Initial conceptual zones:

```text
ATS_CENTER
  Armada-dominated central zone / road / hold area

ATS_WEST_FORWARD
  Ashwalker west forward base zone

ATS_EAST_FORWARD
  Ashwalker east forward base zone

ATS_NORTH_APPROACH
  northern approach / canopy pressure lane

ATS_SOUTH_APPROACH
  southern swamp approach / flank lane
```

Exact bounds are allowed to be rough first.

Use rectangles first. Upgrade to polygons later only if rectangles fail.

Suggested schema:

```json
{
  "schemaVersion": "verdance-zone-map/0.1",
  "mapId": "all_that_simmers",
  "mapName": "All That Simmers",
  "coordinateSystem": "elmos",
  "zones": [
    {
      "zoneId": "ATS_CENTER",
      "label": "Armada Center Hold",
      "shape": "rect",
      "bounds": {
        "xMin": 4096,
        "xMax": 12288,
        "zMin": 4096,
        "zMax": 12288
      }
    }
  ]
}
```

Codex should inspect actual map dimensions from BAR/Spring runtime if possible and replace placeholder coordinates.

## BAR telemetry to export

For each team:

```json
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

For each zone, per team:

```json
{
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
      "unitCountsByDef": {}
    }
  }
}
```

## Metric philosophy

Be lazy.

Prefer BAR’s existing/caster-style abstractions if stable and accessible.

If not stable, compute equivalents directly from live units and runtime UnitDefs.

Minimum metric definitions:

```text
armyValue:
  metal value of mobile combat units

buildPower:
  sum of builder / constructor / nano build power

defensiveValue:
  metal value of static defenses

totalUnitValue:
  metal value of all active units and structures

metalIncome:
  team metal income

energyIncome:
  team energy income
```

The exact implementation may change. The exported field names should remain stable.

## Unit identity rule

Use canonical BAR unit definition names as foreign keys.

Examples:

```text
armpw
armwar
armck
armllt
corgator
corcon
corthug
legcom
```

Do not hardcode a canonical unit database from the React prototypes.

The React unit databases are thematic/mock data.

BAR runtime UnitDefs are the source of truth.

The telemetry packet should send:

```text
unitCountsByDef
```

The upstream tactical system can interpret those names using its own cached catalog.

## Optional unit catalog

Codex may build a separate export later:

```text
bar_unit_catalog.latest.json
```

Suggested shape:

```json
{
  "schemaVersion": "bar-unit-catalog/1.0",
  "source": "BAR runtime UnitDefs",
  "units": {
    "armpw": {
      "name": "armpw",
      "humanName": "Pawn",
      "side": "armada",
      "metalCost": 0,
      "energyCost": 0,
      "health": 0,
      "speed": 0,
      "buildPower": 0,
      "unitGroup": "weapon",
      "isBuilder": false,
      "isFactory": false,
      "isBuilding": false,
      "primaryRole": "mobile_combat"
    }
  }
}
```

This is optional for v1.

## Primary BAR integration route

Use a LuaUI widget and/or LuaRules gadget to inspect match state and emit telemetry.

Required diagnostic commands:

```text
/vaping
/varules
/vahelp
/vaexport
```

Required behavior:

```text
/vaping
  Confirms LuaUI command layer is loaded.

/varules
  Confirms LuaRules gadget is loaded.

/vahelp
  Prints available commands.

/vaexport
  Emits or writes bar-zone-telemetry JSON.
```

## Export transport options

Preferred, in order:

```text
1. Direct write to a known workspace file if BAR allows it safely.
2. Echo compact JSON to infolog.txt with a unique marker.
3. Echo chunked JSON with BEGIN / CHUNK / END markers.
4. Debug-only console print.
```

Normal operation should produce:

```text
Documents/BAR_Verdance_Workspace/outbox/bar_zone_telemetry.latest.json
```

or equivalent.

## Testing sequence for Codex

Codex should run this as a staged test ladder.

### Stage 1 — Load test

Confirm Lua files load.

Expected:

```text
/vaping prints something
/varules prints something
```

If this fails, inspect `infolog.txt` immediately.

### Stage 2 — Minimal export test

Run:

```text
/vaexport
```

Expected:

```text
valid JSON appears in file or infolog
JSON parses locally
schemaVersion exists
map.name exists
teams array exists
```

### Stage 3 — Team telemetry test

Expected:

```text
teams[].unitCountsByDef contains at least one unit
teams[].metrics.totalUnitValue is nonzero if units exist
```

### Stage 4 — Zone map test

Expected:

```text
All That Simmers zone map loads
zones object exists
ATS_CENTER exists
```

### Stage 5 — Zone assignment test

Expected:

```text
at least one live unit is assigned to some zone
zone-level unitCountsByDef is non-empty
```

### Stage 6 — Caster metrics test

Expected:

```text
armyValue
buildPower
defensiveValue
metalIncome
energyIncome
```

exist at team level and preferably zone level.

## What not to do yet

Do not implement these first:

```text
scenario menu integration
full campaign graph mutation
mission seed generation
replay mining
AI campaign planner
hydrology effects
polished HTML dashboard
manual zip-driven install loops
```

The first job is a boring BAR telemetry sensor.

## Relationship to intermediary prototypes

The intermediary React prototypes are useful for understanding desired shape.

They are not authoritative for:

```text
unit stats
unit names
BAR file paths
actual map dimensions
actual Lua APIs
actual caster metric APIs
```

They are authoritative for desired conceptual flow:

```text
campaign intent down
BAR/tactical telemetry up
zones as the bridge
unit counts plus aggregate values
```

## Immediate Codex task

Create or repair a clean local BAR interface project with these files:

```text
BAR.sdd/luaui/Widgets/gui_verdance_bar_exporter.lua
BAR.sdd/luarules/gadgets/game_verdance_bar_bridge.lua
BAR.sdd/singleplayer/verdance_ashes/generated/zone_map_current.lua
Documents/BAR_Verdance_Workspace/outbox/bar_zone_telemetry.latest.json
Documents/BAR_Verdance_Workspace/logs/
```

Then produce a report:

```text
1. Did /vaping work?
2. Did /varules work?
3. Did /vaexport produce valid JSON?
4. Did JSON include map name?
5. Did JSON include teams?
6. Did JSON include unitCountsByDef?
7. Did All That Simmers zone map load?
8. Did any unit get assigned to a zone?
9. What errors appeared in infolog.txt?
10. What is the path to the exported JSON?
```

## Definition of success

v1 succeeds when Codex can produce a valid `bar_zone_telemetry.latest.json` from a live or headless BAR test on All That Simmers.

Minimum success JSON:

```json
{
  "schemaVersion": "bar-zone-telemetry/1.0",
  "map": {
    "name": "All That Simmers",
    "mapId": "all_that_simmers"
  },
  "teams": [
    {
      "teamId": 0,
      "side": "armada",
      "unitCountsByDef": {
        "armpw": 1
      }
    }
  ],
  "zones": {
    "ATS_CENTER": {
      "teams": {}
    }
  }
}
```

After that works, we can iterate upward toward richer metrics, bidirectional mission intent, and tactical summaries.

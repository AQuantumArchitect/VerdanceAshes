# Verdance BAR Interface Layer — Working Charter v0.9

## Role of this layer

The BAR Interface Layer is the practical bridge between Beyond All Reason and the Verdance campaign machinery.

It sits below the tactical translator and above the BAR/Recoil/Spring runtime.

Its job is not to be the campaign brain.

Its job is:

```text
1. Receive tactical/mission intent from the upstream translator.
2. Convert that intent into BAR-readable mission/config files.
3. Observe BAR matches.
4. Export clean telemetry back upward.
5. Stay boring, inspectable, and testable.
```

## System stack

```text
Campaign Overview
  ↓
Tactical Translator
  ↓
BAR Interface Layer  ← this project
  ↓
Beyond All Reason / Spring / Recoil / Lua
```

## New workflow division

### ChatGPT in this thread

This thread owns:

```text
architecture
protocols
schemas
BAR source-code research
implementation specifications
debugging strategy
Codex task packets
fallback design
```

This thread should stop being responsible for:

```text
shipping zip files
guessing Windows paths
being the manual test runner
patching blind Lua syntax errors
coordinating file copy workflows by hand
```

### Local Codex agent

The Codex agent should own:

```text
editing files in the local BAR.sdd workspace
running local scripts
reading infolog.txt
checking Lua syntax
restarting BAR test cycles where possible
building repeatable install scripts
collecting logs
committing snapshots
reporting exact failures
```

## BAR-side design goal

The first stable deliverable is not a campaign loop.

The first stable deliverable is:

```text
BAR can export a useful match/zone telemetry packet.
```

That packet should tell the upstream tactical translator:

```text
what map was played
what zones exist
which teams/factions were present
what units were in each zone
what caster-style values each zone contained
what the terminal result was
```

## Core interface philosophy

Be lazy.

Use the same level of abstraction that a human BAR caster already uses:

```text
army value
build power
defensive value
metal income
energy income
unit counts
map zones
terminal result
```

Do not overbuild tactical interpretation inside Lua.

Do not make Lua decide what a battle “means.”

Lua reports facts.
The tactical translator interprets facts.
The campaign graph mutates campaign meaning.

## Source-of-truth rule for units

BAR is the source of truth for BAR units.

The interface layer should not maintain hand-authored canonical unit stats.

When unit metadata is needed, derive it from runtime `UnitDefs` or from BAR repository unit definitions.

The match telemetry packet should usually pass unit definition strings as foreign keys:

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

The tactical translator can use those strings to look up richer unit meaning.

## Export granularity

The BAR Interface Layer should export both:

```text
A. aggregate metrics
B. raw unit counts by unitDef name
```

Example:

```json
{
  "zoneId": "ATS_CENTER",
  "teams": {
    "0": {
      "side": "armada",
      "metrics": {
        "armyValue": 840,
        "buildPower": 160,
        "defensiveValue": 220,
        "metalIncome": 18,
        "energyIncome": 420
      },
      "unitCountsByDef": {
        "armpw": 12,
        "armwar": 4,
        "armck": 2,
        "armllt": 2
      }
    }
  }
}
```

This keeps the BAR layer simple while preserving enough detail for the tactical translator.

## Zone-map contract

The tactical translator or campaign author provides a zone map.

The BAR Interface Layer uses it to aggregate match facts by zone.

Example:

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
    },
    {
      "zoneId": "ATS_WEST_FORWARD",
      "label": "Ashwalker West Forward Base",
      "shape": "rect",
      "bounds": {
        "xMin": 0,
        "xMax": 4096,
        "zMin": 4096,
        "zMax": 12288
      }
    }
  ]
}
```

For launch, zones should be hand-authored.

Replay-based zone induction is a later tool, not the first implementation.

## First map target

Start with:

```text
All That Simmers
```

Reasons:

```text
no hydrology cycle required
strong campaign layout
clear Armada-dominated center
clear side-zone forward-base concept for Ashwalkers
good first test case for zone telemetry
```

Initial conceptual zones:

```text
ATS_CENTER
  Armada-dominated central contested/held zone

ATS_WEST_FORWARD
  Ashwalker west-side forward base zone

ATS_EAST_FORWARD
  Ashwalker east-side forward base zone

ATS_NORTH_APPROACH
  northern approach / canopy pressure lane

ATS_SOUTH_APPROACH
  southern swamp approach / flank lane
```

Exact coordinates should be authored locally in the map/editor and refined through testing.

## Main telemetry packet

The BAR layer should export:

```json
{
  "schemaVersion": "bar-zone-telemetry/1.0",
  "exportId": "local-20260620-001",
  "matchId": "local-debug-001",
  "campaignId": "verdance_ashes",
  "missionId": "va_001",
  "map": {
    "name": "All That Simmers",
    "mapId": "all_that_simmers",
    "size": {
      "x": 16384,
      "z": 16384
    }
  },
  "frame": 12345,
  "seconds": 411.5,
  "terminal": {
    "isTerminal": true,
    "status": "victory",
    "winnerAllyTeamId": 0
  },
  "teams": [],
  "zones": {}
}
```

## Required top-level fields

```text
schemaVersion
exportId
matchId
map.name
map.mapId
map.size
frame
seconds
terminal
teams
zones
```

## Required team metrics

Each team should include:

```text
teamId
allyTeamId
side
isDead
isAi
metrics.armyValue
metrics.buildPower
metrics.defensiveValue
metrics.totalUnitValue
metrics.metalIncome
metrics.energyIncome
unitCountsByDef
```

## Required zone metrics

Each zone should include, per team:

```text
teamId
allyTeamId
side
metrics.armyValue
metrics.buildPower
metrics.defensiveValue
metrics.totalUnitValue
metrics.unitCount
metrics.combatUnitCount
metrics.builderUnitCount
metrics.structureCount
unitCountsByDef
```

## Preferred metric definitions

The implementation should prefer existing BAR/caster-style values when they are available and stable.

If no stable API exists, compute equivalents from live units and `UnitDefs`.

Minimum definitions:

```text
armyValue
  metal value of mobile combat units

buildPower
  sum of constructor/nano build power

defensiveValue
  metal value of static defenses

totalUnitValue
  metal value of all active non-debris units/structures

metalIncome
  team metal income

energyIncome
  team energy income
```

The exact implementation may evolve, but exported field names should remain stable.

## BAR research notes

BAR already contains useful precedents:

```text
UnitDefs are the right source for runtime unit facts.
BAR has a disabled unit CSV export widget for deriving a unit database.
BAR widgets use WG/shared state patterns for common widget-facing state.
```

Therefore, the implementation should lean toward runtime export and avoid hardcoded unit databases.

## Primary connection strategy

Primary route:

```text
Lua widget/gadget emits structured telemetry.
Telemetry is written or echoed in a parseable form.
Local companion service or Codex reads the result.
Codex validates JSON and stores it in the interface workspace.
```

Preferred final artifact:

```text
bar_zone_telemetry.latest.json
```

## Fallback connection strategies

If direct file writing is unreliable:

```text
Fallback A:
  Emit one-line compact JSON into infolog.txt.

Fallback B:
  Emit chunked JSON into infolog.txt with BEGIN / CHUNK / END markers.

Fallback C:
  Emit multiple smaller packets:
    team summary
    zone summary
    unit counts

Fallback D:
  Use manual copy/paste from in-game console only for emergency debugging.
```

The implementation must not depend on fragile manual file copying as the normal path.

## Codex testing responsibilities

Codex should be given tasks like:

```text
1. Confirm LuaUI widget loads.
2. Confirm LuaRules gadget loads.
3. Confirm /vaping prints.
4. Confirm /varules prints.
5. Confirm /vaexport emits valid JSON.
6. Confirm JSON parses locally.
7. Confirm export includes map name and team list.
8. Confirm All That Simmers zone map loads.
9. Confirm at least one unit is assigned to a zone.
10. Confirm zone metrics are nonzero when units are present.
```

Codex should always inspect `infolog.txt` after a failed test.

Codex should preserve logs and generated exports in a workspace folder.

## Implementation priorities

### Priority 1 — Clean load

The Lua files must load reliably.

Required diagnostic commands:

```text
/vaping
/varules
/vahelp
```

If these fail, nothing else matters.

### Priority 2 — Minimal telemetry

Export:

```text
map name
frame
teams
side/faction
terminal status
team-level unitCountsByDef
```

### Priority 3 — Zone telemetry

Load All That Simmers zone map and export:

```text
zoneId
teamId
unitCountsByDef
unitCount
```

### Priority 4 — Caster-style metrics

Add per-team and per-zone:

```text
armyValue
buildPower
defensiveValue
metalIncome
energyIncome
```

### Priority 5 — Upstream contract

Return the telemetry packet to the tactical translator.

## What to avoid

Avoid:

```text
giant zip-based iteration loops
manual user file-copy debugging
hardcoded unit stats as truth
deep campaign graph logic inside Lua
scenario menu hacking before telemetry works
replay mining before live export works
changing too many layers at once
```

## Definition of version 1 success

Version 1 succeeds when Codex can run or assist a local test that produces:

```text
bar_zone_telemetry.latest.json
```

containing:

```text
All That Simmers map identity
zone definitions loaded
team list
unit counts by team
unit counts by zone
army/build/defense/economy metrics if available
valid parseable JSON
```

Version 1 does not need to advance the campaign graph.

Version 1 does not need to generate missions.

Version 1 does not need replay analysis.

Version 1 is the BAR-facing sensor layer.

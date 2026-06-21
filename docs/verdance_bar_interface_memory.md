# Verdance BAR Interface Memory

Last updated: 2026-06-20

## North Star

The BAR Interface Layer is the boring, inspectable bridge between Beyond All Reason and the Verdance tactical/campaign stack. It is not the campaign brain. Its first job is to observe BAR matches and export stable telemetry upward.

Current stack:

```text
Campaign Overmind
  -> Tactical / Map Comprehension Intermediary
  -> BAR Interface Layer
  -> Beyond All Reason / Spring Recoil / Lua
```

## Immediate Product

Version 1 succeeds when a local or headless BAR test on All That Simmers produces:

```text
C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\outbox\bar_zone_telemetry.latest.json
```

The file must be valid JSON with:

- `schemaVersion = "bar-zone-telemetry/1.0"`
- map identity and actual runtime dimensions
- terminal status
- team list
- team-level `unitCountsByDef`
- five named All That Simmers zones
- zone-level team telemetry
- at least one zone assignment when units are present in a zone

The BAR layer reports facts. The tactical translator interprets meaning. Campaign graph mutation stays out of Lua.

## Current Foothold

Working as of this update:

- `spring-headless.exe` can be launched from the workspace through `scripts/run_headless_smoke.ps1`.
- BAR live SDD Lua patches install through `scripts/install_live_bar_patches.ps1`.
- The Verdance campaign gadget emits parseable result JSON markers into `infolog.txt`.
- `scripts/extract_latest_result.ps1` extracts the latest result into `inbox/latest_va_result.json`.
- Zone-map JSON is staged into BAR VFS as `singleplayer/verdance_ashes/generated/zone_map_current.lua`.
- Headless smoke passes on `All That Simmers v1.1.1` and reports `zoneCount = 5`.

This is not the v1 telemetry exporter yet. It proves that headless launch, BAR Lua loading, JSON marker extraction, and zone-map staging are viable on Windows.

## Authoritative Specs Ingested

Raw briefs are stored in:

- `docs/briefs/working_charter_v0_9.md`
- `docs/briefs/ground_packet_v1_planning_brief.md`
- `docs/briefs/bar_zone_telemetry_exporter_v1_spec.md`

The GitHub RML starter reference is stored in:

- `docs/references/bar-ui-2.0/rml_starter/`

Source URL:

```text
https://github.com/mupersega/Beyond-All-Reason/tree/bar-ui-2.0/luaui/RmlWidgets/rml_starter
```

## Non-Goals For V1

Do not spend first-pass effort on:

- campaign graph mutation
- mission selection
- mission seed generation beyond test fixtures
- scenario menu integration
- replay archive ingestion
- hydrology gameplay effects
- polished HTML or RML dashboard
- full unit lore taxonomy
- React UI implementation

## Implementation Bias

Prefer:

- runtime `UnitDefs` as source of truth
- BAR unitDef names as foreign keys
- compact/chunked infolog JSON markers if direct file writes are unreliable
- repeatable headless tests
- scripts that create backups before touching live BAR files
- small, inspectable Lua helpers over large speculative systems

Avoid:

- hardcoded unit databases from prototypes
- manual file-copy testing loops
- deep campaign meaning inside Lua
- changing UI, telemetry, mission generation, and graph mutation at once

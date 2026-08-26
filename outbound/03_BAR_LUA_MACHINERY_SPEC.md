# Outbound Briefing 03: BAR <-> Lua Machinery Specification

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Mutator Location:** [`mod/VerdanceAshes.sdd`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/mod/VerdanceAshes.sdd)

---

## 1. Overview of BAR Lua Layer

The BAR game engine runs custom campaign logic through a dedicated game archive mutator (`VerdanceAshes.sdd`) loaded via `GameType=Verdance Ashes $VERSION`. This archive contains:

1. **LuaRules Gadget:** [`game_verdance_campaign.lua`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_campaign.lua) (92 KB) — Handles campaign setup, unit tracking, hero tagging, objective automation, zone telemetry collection, and game-end result serialization.
2. **LuaUI Objective HUD:** [`gui_verdance_objectives.lua`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/mod/VerdanceAshes.sdd/luaui/widgets/gui_verdance_objectives.lua) (19 KB) — Displays briefing cards, objective targets, kill counters, extraction zone countdowns, and debrief overlays.
3. **LuaUI Hero Tags Widget:** [`gui_verdance_hero_tags.lua`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/mod/VerdanceAshes.sdd/luaui/widgets/gui_verdance_hero_tags.lua) — Renders world-space badges and health bars over hero units (Vane and Ketha).
4. **Campaign Overmind Widget:** [`campaign_overmind_widget.lua`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/mod/VerdanceAshes.sdd/luaui/widgets/campaign_overmind_widget.lua) — Communication bridge between LuaUI and LuaRules.

---

## 2. In-Game Diagnostic Console Commands

The gadget exposes the following chat commands in-game (`Enter` -> type command):

| Command | Purpose | Output / Marker |
|---|---|---|
| `/vahelp` | Displays available Verdance chat commands | Chat log |
| `/vaping` | Health check verification | `VA_PING_WIDGET_OK` |
| `/varules` | Rules health check verification | `VA_PING_RULES_OK` |
| `/vastatus` | Prints active campaign mission ID, objective status, and hero health | Chat log |
| `/vazones` | Prints current zone unit counts and faction dominance | Chat log |
| `/vaexport` | Triggers immediate manual export of telemetry | `VA_EXPORT_OK` |
| `/vawin` | Forces instant victory status | `VA_RESULT_JSON_*` |
| `/vafail` | Forces instant defeat status | `VA_RESULT_JSON_*` |
| `/vapartial` | Forces partial victory status | `VA_RESULT_JSON_*` |
| `/luarules vatest_killobjective` | Cheat command: Instantly destroys all tracked objective centerpiece structures | In-game explosion + Victory trigger |

---

## 3. Telemetry Collection & Zone Units

Every 15 seconds in-game, `game_verdance_campaign.lua` polls unit locations against the current map's authored zone bounds (`data/zone_maps/authored/*.json`).

### Tracked Telemetry Metrics:
- **Zone Occupancy:** Unit count per team per zone.
- **Metal / Defense Density:** Metal extractors, solar/wind generators, and turrets built per zone.
- **Zone Entanglement:** Faction combat pressure along adjacent zone boundaries.
- **Hero State:** Health percentage, position, and damage taken for Vane and Ketha.

At mission end, the gadget compiles `outbox/bar_zone_telemetry.latest.json`.

---

## 4. Infolog Result Protocol

BAR write access directly to disk can be restricted by operating system permissions. To ensure 100% reliable transport, the gadget writes JSON payloads directly to BAR's `infolog.txt` using structured string markers:

```text
VA_RESULT_JSON_START
{"schemaVersion":"verdance-match-result/1.0","campaignId":"verdance_ashes","missionId":"va_002","missionNumber":2,"status":"defeat","reason":"hero_lost_ketha","elapsedMinutes":4.12,"extractionStatus":"contested","destroyedObjectiveIds":[],"objectiveResults":[{"id":"EOH_CORTEX_DEALER_RELAY","status":"active"}]}
VA_RESULT_JSON_END
```

And for translation matrix spectra:

```text
VA_TRANSLATION_PACKET_START
{"schemaVersion":"bar-zone-telemetry/1.0","nodes":...}
VA_TRANSLATION_PACKET_END
```

The PowerShell script `scripts/extract_latest_result.ps1` monitors `infolog.txt`, extracts the JSON payload between the `START` and `END` tags, and writes `inbox/latest_va_result.json`.

---

## 5. Objective Automation & Extraction Logic

1. **Destruction Objectives (`economy_disrupt`, `strike_relay`, `destroy_key_structure`):**
   - The gadget monitors objective structure IDs (e.g. `GF_ARMADA_ENERGY_WORKS`, `EOH_CORTEX_DEALER_RELAY`).
   - When all objective targets are destroyed, `VA_OBJECTIVE_TARGET_DOWN` fires, updating HUD state to "Extract Now".
2. **Presence Objectives (`seize_lane`, `gate_control`):**
   - The gadget monitors player unit density in target zones. When player forces maintain majority density for 30 consecutive seconds, the objective clears.
3. **Extraction Requirement:**
   - Player must bring the Commander / surviving heroes into the designated extraction zone (`extractionZoneId`).
   - If extraction zone is clear of enemy combat units: `extractionStatus = "clean"`.
   - If enemy units are in the zone during extraction: `extractionStatus = "contested"`.
4. **Hero Loss Trigger:**
   - If a mission-critical hero (Vane or Ketha) dies, the gadget immediately triggers a match defeat with `reason = "hero_lost_ketha"` or `"hero_lost_vane"`.

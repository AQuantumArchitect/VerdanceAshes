# Outbound Briefing 01: Project Overview & System Architecture

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Workspace:** [BAR_Verdance_Workspace](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace)

---

## 1. Executive Summary

**Verdance's Ashes** is an open-ended, procedural single-player campaign engine built on top of **Beyond All Reason (BAR)**. Rather than relying on rigid, pre-scripted campaign trees, Verdance dynamically compiles playable BAR scenarios based on an evolving macro campaign state. It captures detailed battlefield telemetry during play, processes this data through a mathematical density matrix / spectral eigensolver, and updates an abstract "quantum graph" that drives story events, companion reactions, faction relationships, economy scarcity, and future mission objectives.

---

## 2. Core Operational Loop

The system operates via a continuous file-backed feedback loop:

```
+-------------------------------------------------------------------------+
|                              BAR MATCH                                  |
|  Player launches mission via mod archive (VerdanceAshes.sdd).           |
|  In-game gadget (game_verdance_campaign.lua) tracks kills, zones, HUD, |
|  hero health, and objective status.                                     |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                         INFOLOG TELEMETRY EMISSION                      |
|  At game end, Lua emits JSON markers (VA_RESULT_JSON_*,                |
|  VA_TRANSLATION_PACKET) into BAR's infolog.txt.                         |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                        RESULT & TELEMETRY EXTRACTION                    |
|  Powershell scripts (extract_latest_result.ps1 &                        |
|  extract_latest_translation.ps1) parse infolog markers to               |
|  inbox/latest_va_result.json and inbox/latest_va_translation.json.     |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                       PYTHON STORY ENGINE ADVANCEMENT                   |
|  verdance_story_engine_v1.py ingests match results, evaluates           |
|  Hermitian density matrix spectra, updates graph scalars, adjusts       |
|  companion status (Ketha), and mutates state/campaign_state.json.        |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                   MISSION INTENT & STORY EVENT EMISSION                 |
|  Engine writes outbox/next_mission_intent.json and                      |
|  outbox/story_events.latest.json containing briefing lines, debriefs,   |
|  and objective specs.                                                   |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                      PLAYABLE SCENARIO COMPILATION                      |
|  build_next_mission_v1.ps1 compiles intent into startscripts & scenario |
|  seeds in mod/VerdanceAshes.sdd/singleplayer/missions/.                 |
+-------------------------------------------------------------------------+
```

---

## 3. Directory Layout & Source-of-Truth Hierarchy

```
BAR_Verdance_Workspace/
├── .agents/                   # Internal agent infrastructure (work orders, experiment logs)
├── data/                      # Authored static data (map pool, zone maps, scenario templates, story lines)
│   ├── map_pool/              # canonical seven_maps.json catalog
│   ├── story/                 # ketha_voice.json voice table
│   └── zone_maps/authored/    # Authored map zone definitions (7 maps)
├── docs/                      # Developer documentation & briefs
├── headless_runs/             # Log archives of automated headless balance & smoke runs
├── inbox/                     # Extracted JSON payloads from recent BAR matches
├── mod/                       # BAR Mutator archive (VerdanceAshes.sdd)
│   └── VerdanceAshes.sdd/     # Lua rules gadget, UI widgets, singleplayer seed files
├── outbox/                    # Live materialized contracts (next_mission_intent.json, story_events, etc.)
├── outbound/                  # 10 Outbound Briefing documents for Web GUI Adviser
├── playable_runs/             # Playable variant manifests & save game pointers
├── reports/                   # Performance reports, AI baseline benchmarks, emergent graph analyses
├── scripts/                   # PowerShell orchestration wrappers & automation scripts
├── state/                     # Active campaign truth (campaign_state.json)
└── tools/                     # Python story engine (verdance_story_engine_v1.py)
```

---

## 4. Key File Contracts

1. **Active Campaign State**: [`state/campaign_state.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/state/campaign_state.json) (Schema: `verdance-campaign-state/1.0`)
2. **Next Mission Intent**: [`outbox/next_mission_intent.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/outbox/next_mission_intent.json) (Schema: `verdance-mission-intent/1.0`)
3. **Story Events Output**: [`outbox/story_events.latest.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/outbox/story_events.latest.json) (Schema: `verdance-story-events/1.0`)
4. **Latest Extracted Match Result**: `inbox/latest_va_result.json` (Schema: `verdance-match-result/1.0`)
5. **Latest Translation Matrix Packet**: `inbox/latest_va_translation.json`

---

## 5. Main Script Entrypoints & One-Click Launchers

- `PLAY_SESSION_V1.bat` / [`scripts/play_session_v1.ps1`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/scripts/play_session_v1.ps1): Complete one-click play loop watcher. Launches BAR, waits for match end, extracts infolog result, advances campaign state, and builds the next mission.
- `BUILD_NEXT_MISSION_V1.bat` / [`scripts/build_next_mission_v1.ps1`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/scripts/build_next_mission_v1.ps1): Compiles intent into scenario files without launching BAR.
- `01_extract_latest_result.bat`: Extracts latest match JSON markers from BAR's `infolog.txt`.
- `02_advance_campaign_and_install_seed.bat`: Runs Python story engine to advance state and build next mission.
- `RUN_HEADLESS_BALANCE_TEST.bat` / [`scripts/run_headless_balance_test.ps1`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/scripts/run_headless_balance_test.ps1): Executes headless BAR match with AI in player seat to probe mission balance.

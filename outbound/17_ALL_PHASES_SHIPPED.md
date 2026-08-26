# All phases shipped — Systems Revamp (2026-07-25)

Head Hancho executed Phase 1–4 of the play-driven systems revamp.

---

## Phase 1 (already live, retained)

| WO | Feature |
|---|---|
| 030 | `arcProfile` knob table |
| 031 | Plain-English mission card |
| 032 | 0 player commanders + sweep |
| 034/035 | Static bases, escalation modes |
| 038 | Ally power curve |
| 040 | TIME + PHASE HUD |

---

## Phase 2

| WO | Feature | How to feel it |
|---|---|---|
| **033** | **Unit printer** | Lab at deploy, locked to `leggob`, metal/energy trickle, starter goblins |
| **039** | **Adjacent deploy/target/extract** | Compiler + story engine force short walks (no EOH marathon) |
| **041** | **Minimap zone overlay** | Zone rects on minimap; toggle `/vazones` `/vazoneslabels` |

---

## Phase 3

| WO | Feature | How to feel it |
|---|---|---|
| **020a** | **World zone graph** | `data/zone_maps/world_zone_graph.v1.json` — 45 nodes, 83 edges (76 same_map + 7 strategic) |
| **042** | **Debrief next-mission pick** | End screen: press **1/2/3** (or `/vanext N`). Writes `VA_NEXT_SORTIE_CHOICE` + best-effort file. Extract/advance honors `outbox/next_sortie_choice.json` |
| **043** | **Capability probe** | Gadget logs `VA_PROBE_IO` / `VA_PROBE_RELOAD` at frame 45. Full Reload loop still external-fallback |

---

## Phase 4

| WO | Feature | How to use |
|---|---|---|
| **036** | **Barbarian hard mode** | Set intent `difficulty.enemyAI = "barbarian"` or `environment.hardMode = true` before build → AI shortName `BARb` |
| **037** | **GF commander solar soup** | Debrief candidate **3** (sandbox) or `flavor = "com_solar_farm"` — does **not** sweep enemy coms; production allowed |

---

## Play path (unchanged one bat)

```
C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\PLAY_SESSION_V1.bat
```

1. Start paused → mission card  
2. Timer + phase on HUD  
3. Minimap zones visible  
4. 0 player coms, unit printer, adjacent LZ  
5. End → pick 1/2/3 → exit → advance uses pick  

---

## Artifacts

| Path | Notes |
|---|---|
| `data/zone_maps/world_zone_graph.v1.json` | Atlas |
| `tools/build_world_zone_graph.py` | Generator |
| `tools/validate_world_zone_graph.py` | Validator |
| `mod/.../gui_verdance_zone_minimap.lua` | Minimap |
| `mod/.../game_verdance_capability_probe.lua` | WO-043 |
| `outbound/16_PHASE1_SYSTEMS_REVAMP.md` | Phase 1 note |

---

## Still external (by design)

- Python story engine still owns campaign_state math  
- `PLAY_SESSION_V1.bat` still launches + advances (Reload loop only if probe green + future WO-045)  
- RmlUi full deck still gated  

---

*Ship complete. Play and rant.*

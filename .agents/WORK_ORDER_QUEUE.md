# Work Order Queue — Head Hancho

Source of orders: **HEAD_HANCHO** (self-issued) + operator rants.  
Web GUI Adviser packets retired 2026-07-24.

| Work Order ID | Title | Priority | Status | Output |
|---|---|---|---|---|
| WO-000 | Onboarding outbound 01–10 | HIGH | COMPLETED | outbound/01–10 |
| WO-001 | Zone adjacency | P0 | COMPLETED | zone_adjacency.json |
| WO-002 | clans → nullmercs | P0 | COMPLETED | state + engine |
| WO-007 | Zone flip on victory | P0 | COMPLETED | process_result |
| WO-003 | Sortie order intake | P0 | COMPLETED | next_sortie_order.json |
| WO-008 | Retire hero_lost_restart | P1 | COMPLETED | gadget + advance |
| WO-006 | Wreck rule named markers | P1 | COMPLETED (roster) | namedOutcomes |
| WO-005 | Character XP registry | P1 | COMPLETED | characters{} |
| **WO-004** | Ten-minute sortie shape | P1 | **COMPLETED (build)** | outbound/WO-004_REPORT.md |
| **WO-010** | Forward extraction | P2 | **COMPLETED** | outbound/WO-010_REPORT.md |
| **WO-101** | Engine capability probe | P0 DCO-02 | **COMPLETED** | outbound/WO-101_REPORT.md |
| B0 | Legal va_003 contract | P0 | **COMPLETED** | next_sortie_order + intent |
| HH-A | Head Hancho succession docs | P0 | **COMPLETED** | PARTNER_IDENTITY, 12 charter |
| HH-B | Start + end pause | P0 | **COMPLETED** | game_verdance_campaign.lua unsynced |
| HH-C | Named rez identity | P0 | **COMPLETED** | rez_grace + def/pos match |
| WO-030..045 | Phases 1–4 systems revamp | P0 | **COMPLETED** | outbound/17_ALL_PHASES_SHIPPED.md |
| WO-020a | World zone graph atlas | P0 | **COMPLETED** | data/zone_maps/world_zone_graph.v1.json |
| WO-033 | Unit printer | P0 | **COMPLETED** | leglab → leggob |
| WO-039 | Adjacent deploy/extract | P0 | **COMPLETED** | build + story engine |
| WO-041 | Minimap zones | P0 | **COMPLETED** | gui_verdance_zone_minimap.lua |
| WO-042 | Debrief next pick | P0 | **COMPLETED** | keys 1–3 + extract honor |
| WO-043 | Capability probe | P1 | **COMPLETED** | VA_PROBE_* logs |
| WO-036/037 | Hard mode + GF soup | P1 | **COMPLETED** | BARb / com_solar_farm |
| WO-005b | XP calibration | P1 | QUEUED | — |
| WO-006b | Enemy named cast spawn | P1 | QUEUED | — |
| WO-009 | Measurement coverage | P2 | QUEUED | — |
| WO-102+ | RmlUi port | P2 | BLOCKED on array smoke | — |
| **WO-044** | Kernel graph lock | P0 | **COMPLETED** | outbound/44 |
| **WO-045** | Overnight kernel phases 1–5 | P0 | **COMPLETED** | outbound/45 · 76 tests |
| WO-045b | Player-rig hub/shop/Deploy | P0 | **QUEUED river** | pkt-bar-player-rig-hub-shop-deploy |
| WO-045c | Mode B Reload travel | P1 | **QUEUED river** | pkt-bar-mode-b-reload-travel |
| WO-045d | Lua tenebrium file split | P2 | **QUEUED river** | pkt-bar-lua-tenebrium-file-split |
| WO-045e | Cloud real shell dumps | P1 | **QUEUED river** | pkt-bar-cloud-shell-bake-real-dumps |
| WO-045f | Capture node claims | P2 | **QUEUED river** | pkt-bar-capture-node-claims |
| WO-045g | Seven-map shell recipes | P1 | **QUEUED river** | pkt-bar-seven-map-shell-recipes |

## Protocol

- Operator rants → Hancho designs + executes  
- Optional `VA-SORTIE/1` still accepted via `validate_sortie_contract.py`  
- Truth: `state/campaign_state.json`  
- Always report full absolute paths + lengths to operator

# Head Hancho Status Board

**Last updated:** 2026-07-25 (app shell + proxy story + customer My Games release)  
**Role:** Adviser + Boots (GUI brain dead)  
**Operator note:** Prefer build over unit-test thrash unless asked.

## Campaign snapshot

| Field | Value |
|---|---|
| Mission | **va_005** READY — Koom, Arc **contested_front** |
| Arc | 0 coms · unit printer · static_bases · ally 0.25 · esc light |
| Layout | Adjacent deploy/extract enforced |
| Loop | **Mode A same-map continue** + **session host auto-relaunch** |
| Graph | **world_zone_graph.v1.json** 45 nodes / 83 edges |
| Seed | Live BAR + workspace outbox (`continueRules` baked) |
| AI proxy | **quantum-BAR-AI fair first arc CLEARED** @ diff 1.0 (tools+belief only) |

## Work order board

| ID | Title | Status |
|---|---|---|
| Phase 1–4 | Systems revamp | SHIPPED — outbound/17 |
| **WO-050..053** | Mode A soft terminal + continue | **SHIPPED** — outbound/18 |
| **WO-057** | Session host multi-mission | **SHIPPED** |
| **WO-054** | Capability probe v2 | **SHIPPED** (matrix pending live play) |
| **WO-061** | Package START_HERE + docs | **SHIPPED** skeleton |
| **WO-070** | quantum-BAR-AI player proxy MVP | **SHIPPED** — outbound/19 |
| **WO-074** | Fair first arc (player context only) | **CLEARED** — outbound/20 |
| **WO-076** | Ant subscription brain on fair arc | **LIVE** 5/5 — outbound/21 |
| **WO-077** | App shell + story HTTP/Lua + customer export | **SHIPPED** — outbound/22 |
| WO-055/056 | Mode B Reload travel | PENDING (gate on matrix) |
| WO-058..060 | Prebaked packs / Lua-thin | PENDING |
| WO-062..065 | Public zip / Discord / Reddit | PENDING |
| WO-071 | Feed BAR telemetry → FairHUD | PENDING |
| WO-072 | Live Lua seat / GiveOrder bridge | PENDING |
| WO-073 | yurt umweltd world promotion | PENDING |
| WO-075 | GrokToolAgent overnight fair arc | PENDING (API path) |

## Play now

Human: `PLAY_SESSION_V1.bat` (Mode A continues)  
AI proxy (free): `RUN_BEAT_FIRST_ARC.bat`  
AI proxy (**ant subscription**): `RUN_BEAT_FIRST_ARC_ANT.bat`  

- Outbound: `outbound/20_FAIR_FIRST_ARC_CLEARED.md` · `outbound/21_ANT_SUBSCRIPTION_BRAIN.md`
- Module: `tools/quantum_bar_ai/` (`ant_client`, `ant_agent`, `fair_sim`, `beat_first_arc`)
- Brain path: yurt `ant_brain.spawn_grok` + `~/.grok/auth.json` (not XAI API $)

## Engine

- BAR data: `...\Beyond-All-Reason\data`
- Engine: `recoil_2025.06.24` — Reload still gated; Mode A does not need it
- Umwelt: `ws-win\umwelt` + Grok key in `yurt\config\yurt.env`

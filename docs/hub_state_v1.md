# hub_state.v1 + cyoa_node.v1

Stable contracts for the **HTML war-map hub** (showoff → Steam shell).  
Generated from `campaign_state.json` + `war_map.json` + `world_zone_graph.v1.json`.  
Consumed by `app/showoff/` (and later the Electron/Tauri shell).

## hub_state.v1

```json
{
  "schemaVersion": "verdance-hub-state/1.0",
  "campaignId": "verdance_ashes",
  "missionNumber": 1,
  "seed": 28,
  "generatedAt": "ISO-8601",
  "tagline": "Aces, a war map, and sorties that feed the story.",
  "reputation": {
    "armada": 0,
    "cortex": 0,
    "nullmercs": 0,
    "sev": 0
  },
  "bay": {
    "unlocked": false,
    "threshold": 40,
    "label": "Null Mercs mod bay",
    "hint": "Bay locked — raise Null Mercs reputation."
  },
  "aces": [
    {
      "id": "vane",
      "name": "Ash-Captain Vane",
      "faction": "ashwalkers",
      "unitDef": "legbal",
      "level": 2,
      "rank": "Runner",
      "campaignXp": 118.4,
      "wounds": 0,
      "status": "active",
      "scars": [],
      "deployable": true,
      "bonds": { "ketha": 10 }
    }
  ],
  "regions": [
    {
      "mapId": "greenest_fields",
      "displayName": "Greenest Fields",
      "descriptor": "The Synthesized Utopia",
      "family": "economy",
      "control": "contested",
      "dominantEnemy": "armada",
      "threatBand": "light",
      "controlCounts": {},
      "selectable": true
    }
  ],
  "node": { "...": "see cyoa_node.v1 — current beat" },
  "lastResult": null,
  "history": [],
  "sessionMode": "same_map",
  "occupationModel": "living_shell",
  "factionBanks": { "armada": 0, "cortex": 2, "nullmercs": 0, "ashwalkers": 0 },
  "tenebrium": 0,
  "commerce": { "...": "see hub commerce surface below" },
  "flags": {
    "mode": "hub",
    "deployStub": true,
    "shopSurface": true,
    "deployCompileLaunch": true
  }
}
```

### Field notes

| Field | Owner | Notes |
|---|---|---|
| `aces` | From `campaign_state.roster.heroes` + `characters` | Playtest: surface Vane + Ketha first; others read-only |
| `bonds` | Optional on characters | v1: only `vane↔ketha` required |
| `bay` | Derived from `reputation.nullmercs` | UI stub until G8; never blocks Deploy |
| `regions` | From `war_map.regions` | Click → filters contracts / flavor |
| `node` | Generator | Current CYOA beat (choices) |
| `lastResult` | After sortie | Tokens for coupling: zone, verdict, xpDeltas |
| `flags.deployStub` | Shell | true until real BAR launch wired |
| `flags.shopSurface` | Shell | commerce catalog projected into `commerce.shop` |
| `flags.deployCompileLaunch` | Shell | Deploy → host stamp + intent + build + optional launch |
| `graph` | From `campaign_state.graph` | q0/q2/q6/q7 campaign qubits for density room |
| `spectral` | `lastSpectral` or derived | λ max, energy, participation, factionWeights |
| `pathSignal` | Campaign path A/B/C | Shown under spectrum |
| `sessionMode` | Kernel paint | Default `same_map` (Mode A focus chain) |
| `occupationModel` | Kernel paint | Default `living_shell` |
| `factionBanks` | Kernel + bag | Armada crisis → 0; player banks track Tenebrium |
| `tenebrium` | Commerce bag | Top-level paint for badges / HUD |
| `commerce` | Catalog + bag | Shop shelf, deploy kit, balances (read-only build) |

### Density matrix room (UI)

Sourced from earlier prototypes:

- `inbox/.../tactical_map_comprehension_matrix.jsx` — local ρ heat grid + entanglement SVG  
- `inbox/handoff_v3/verdance_command_deck.jsx` — graph scalars + spectrum bar  

Hub builds **local ρ** for the focused theater from zone-board geometry + graph pressure
(off-diagonal coherence). Graph scalars are global campaign axes (not map-local).

---

## cyoa_node.v1

```json
{
  "id": "hub_open_m1",
  "kind": "choice",
  "speaker": "ketha",
  "text": "Front is quiet. Pick a scar before Armada finishes the pour.",
  "regionHint": "greenest_fields",
  "choices": [
    {
      "id": "c_raid_gf",
      "label": "Raid Greenest Fields eco",
      "kind": "deploy",
      "effect": {
        "mapId": "greenest_fields",
        "contractKind": "eco_raid",
        "edgeId": null,
        "deployAces": ["vane", "ketha"]
      }
    },
    {
      "id": "c_talk",
      "label": "Talk with Ketha",
      "kind": "talk",
      "effect": {
        "social": "vane_ketha_hearth",
        "bondDelta": { "vane": { "ketha": 2 } }
      }
    },
    {
      "id": "c_rest",
      "label": "Rest the aces",
      "kind": "rest",
      "effect": {
        "healWounds": 1,
        "stressDelta": -5
      }
    },
    {
      "id": "c_merc",
      "label": "Take a Null Mercs contract",
      "kind": "deploy",
      "effect": {
        "mapId": "koom_valley",
        "contractKind": "seize_lane",
        "repDelta": { "nullmercs": 3 }
      }
    }
  ]
}
```

### Choice kinds

| `kind` | Meaning | Playtest |
|---|---|---|
| `deploy` | Commit sortie (shell → BAR later) | Opens C&C board → Deploy |
| `shop` | Open broker shop panel | Catalog shelf from `commerce.shop` |
| `talk` | Interpersonal membrane beat | Template dialogue + bond delta |
| `rest` | Heal / lower stress | Local state only |
| `travel` | Change focus region without sortie | Optional |
| `bay` | Open mod bay | Locked until G8 |

---

## hub commerce surface (`commerce`)

Built by `tools/build_hub_state_v1.py` from `data/commerce/commerce_catalog.json`
+ `state/campaign_state.json` → `commerce`. **No story-engine mutation** in the
builder; the HTML shop may demo-buy in-memory and download a receipt JSON.
Live campaign purchase remains `purchase_listing` on the engine / host path.

```json
{
  "schemaVersion": "verdance-hub-commerce/1.0",
  "tenebrium": 0,
  "scrapCredits": 40,
  "resource": { "id": "tenebrium", "label": "Tenebrium", "shortLabel": "Tnb" },
  "shop": [
    {
      "id": "crash_of_brutes",
      "label": "Crash of Brutes",
      "kind": "purchase_package",
      "tenebriumCost": 0,
      "creditCost": 180,
      "available": false,
      "blockedReason": "need 180 scrap credits",
      "owned": false,
      "tags": ["merc", "armor"]
    }
  ],
  "deployKit": [
    { "listingId": "punch_of_thugs", "kind": "loan_package", "unitDef": "corthud", "count": 6, "loan": true }
  ],
  "owned": {},
  "upgrades": {},
  "notes": "Tenebrium is black-hole metal…"
}
```

Shelf gates mirror the engine (rep, arc, cost, already-owned, requires) for paint only.

### Effects (minimal)

- `mapId`, `contractKind`, `deployAces[]` — stamp next mission
- `bondDelta`, `healWounds`, `stressDelta`, `repDelta` — hub-only advances
- `edgeId` — optional world_zone_graph edge for legality later

---

## Generator

- Script: `tools/build_hub_state_v1.py`
- Inputs: `state/campaign_state.json`, `outbox/war_map.json`, `data/commerce/commerce_catalog.json`
- Output: `app/showoff/hub_state.json` (+ embed helper for offline HTML)
- Showoff entry: `app/showoff/index.html` (hub + shop + Deploy board)
- Story autoplay (old demo): `app/showoff/story_autoplay.html`

## Coupling rule

Every post-choice or post-result line should be able to cite at least one **token**:  
`mapId`, `verdict`, `aceId`, `xpDelta`, `wound`, `rep.nullmercs`, `control`.  
If the text cannot point at a token, it is flavor-only and must not claim causality.

---

## deploy_plan.v1 (C&C board layer)

Opened from a `deploy` choice. Player marks the **zone board** for the chosen map
before the sortie is committed (shell stamp → BAR seed later).

```json
{
  "schemaVersion": "verdance-deploy-plan/1.0",
  "mapId": "greenest_fields",
  "contractKind": "eco_raid",
  "deployAces": ["vane", "ketha"],
  "arcId": 2,
  "maxCaptureMarks": 2,
  "marks": {
    "deployZoneId": "GF_SE_STAGING",
    "extractZoneId": "GF_SE_STAGING",
    "captureZoneIds": ["GF_SE_ENERGY_WORKS", "GF_NORTH_DESERT_EDGE"]
  },
  "markMode": "capture"
}
```

### Arc caps (C&C escalation)

| Arc | Missions | Max **capture** marks | Intent |
|---|---|---|---|
| 1 First Scar | 1–5 | **1** | Single strike objective |
| 2 Second Scar | 6–10 | **2** | Dual capture / multi-pressure |
| 3 Third Scar | 11–15 | **3** | Multipressure climax |

Also always set (auto-defaults, player can re-mark):
- **Deploy** zone (one) — where the warband stages  
- **Extract** zone (one) — usually same as deploy early on  

Zone boards: `tools/build_zone_boards_v1.py` → `app/showoff/boards.embed.js`  
(`window.ZONE_BOARDS[mapId].zones[]` with bounds + capturable flags).

### Seed stamp (BAR glue — G2)

`deploy_plan.marks.captureZoneIds[0]` → primary `objective.targetZoneId`  
additional ids → `secondaryCaptureZoneIds` on seed + minimap secondary paint  
`deployZoneId` / `extractZoneId` → `deploymentZoneId` / `extractionZoneId`  
`choiceId` → `hubChoiceId` on seed; `deployAces[]` carried for briefing

Pipeline:

```
tools/stamp_deploy_plan_v1.py   → outbox/next_sortie_order.json
tools/hub_host_v1.py POST /api/deploy[?launch=1]
  → stamp → story intent → build_next_mission → optional play_session
```

Offline HTML (`file://` or `SHOW_OFF.bat`) still runs the CYOA as a **stub** and downloads
`hub_deploy_plan.json` (+ stub result). Live BAR path: `app\bin\HUB_HOST.bat` →
http://127.0.0.1:8770/ — **Deploy** POSTs `deploy_plan.v1` to
`POST /api/deploy?launch=1` → stamp → story intent → `build_next_mission` →
`play_session` (compile + launch). Shop is always painted from hub_state commerce.

### Result pull (G4)

After a BAR sortie:

```
scripts/extract_latest_result.ps1  → inbox/latest_va_result.json
python tools/apply_result_to_hub_v1.py
  → advance --write-state + hub_state rebuild
  → outbox/hub_result.latest.json
```

Hub host: `POST /api/advance?extract=1`. Hub UI: **Pull BAR result** (also polls `/api/result`).
Density-matrix room: **ρ Manifold** tab (local ρ + graph qubits + `campaignRho` axes).

### Mode A integration

- After each advance, `campaign_state.sessionHomeMap` locks the theater just fought.
- Hub stamps (`source: hub_deploy_plan`) are **consumed** once that map is played so the
  next materialize walks Mode A / quest_batch (debrief **1/2/3** picks are kept).
- Hub open-node prefers same-map continues; optional travel contracts are labeled as hops.
- Live shop: `POST /api/purchase` → `purchase_listing` → campaign bag + hub rebuild.

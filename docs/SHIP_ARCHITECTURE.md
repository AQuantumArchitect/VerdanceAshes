# Verdance's Ashes — Steam ship architecture

**Kernel, not trappings.** BAR is the combat seat. The campaign brain lives outside BAR.

## Phases

| Phase | Name | Status | Entry |
|---|---|---|---|
| 0 | Forge loop | live | `app\bin\forge\`, `tools/*` |
| 1 | Single launcher + kernel API | **live** | root `PLAY.bat` · `python -m verdance_kernel launch` |
| 2 | BAR bridge (auto bring-home) | **live** | auto with launcher · `outbox/bridge.latest.json` |
| 3 | Steam freeze (cloud / achievements) | **stub** | `state/steam/` |
| 4 | In-BAR campaign surface | **stub** | `outbox/campaign_surface.latest.json` |
| 5 | Consolidated ship | **live** | `SHIP.bat` · `scripts\ship.ps1` → `export\dist\` |

## Product process tree

```
PLAY.bat / python -m verdance_kernel launch
  └─ CampaignKernel
       ├─ HTTP :8770  (war map UI — browser or pywebview)
       ├─ BarBridge   (watch results → apply_result)
       └─ Steam stubs (mirror + achievements log)
            │
            ├─ stamp → intent → build_next_mission
            └─ play_session_v1 → BAR + VerdanceAshes.sdd
```

## Frozen API (`CampaignKernel`)

| Method | Role |
|---|---|
| `get_hub_surface()` | War-map CYOA projection |
| `commit_deploy(plan, launch=)` | Stamp → intent → build → optional BAR |
| `apply_result(extract=)` | Extract + advance + hub refresh |
| `purchase(listingId)` | Broker |
| `rebuild_hub()` | Rebuild hub_state + surface |
| `write_campaign_surface()` | Phase 4 flat file for BAR |
| `status()` | Caps, phases, steam, bridge |

HTTP (compat with showoff):

- `GET /api/status|hub-state|result|session|phases|steam|surface`
- `POST /api/deploy|advance|purchase|rebuild-hub`

## Phase 3 — Steam (when AppID lands)

1. Bind Steamworks in the launcher EXE (not in BAR).
2. Map `state/steam/cloud/campaign_state.json` → Cloud remote storage.
3. Map `state/steam/unlocked.json` → `SteamUserStats()->SetAchievement`.
4. Depot layout: shell + kernel + mod + content; BAR remains external dependency.

## Phase 4 — In-BAR

- Shell remains primary CYOA.
- Mutator may display `campaign_surface.latest.json` between sorties (`/vasurface` when wired).
- Mode A continues stay in-seat (already shipped).

## Packaging path

1. **Now (v0.8 consolidation):** workspace root `SETUP.bat` + `PLAY.bat` → kernel  
2. **Next:** single `scripts/ship.ps1` → `export/dist/` self-contained (WP3)  
3. **Then:** freeze with PyInstaller / Nuitka → `VerdanceAshes.exe`  
4. **Later:** Tauri/Wails; Steam AppID, depots, cloud, achievements  

**Do not** treat `Documents\My Games\VerdanceAshes` as a second product — see `docs/DEPLOY_TRUTH.md`.

## What not to ship to players

- Operator bat forest
- Manual JSON downloads as a required step
- “Wire open / map only” as primary language (shell softens this)
- Density-matrix engine terms outside Advanced
- Thin brochure exports that open offline HTML and call it PLAY

## Dev notes

```
# Product (canonical)
SETUP.bat
PLAY.bat

# Smoke without launching BAR
powershell -File scripts\player\smoke_play_path.ps1

# Kernel only
python -m verdance_kernel serve --no-browser

# Status / surface
python -m verdance_kernel status
python -m verdance_kernel surface
python -m verdance_kernel phases

# Optional embedded window
pip install pywebview
```

Module: `tools/verdance_kernel/` (on `PYTHONPATH` via `app\bin\_env.bat`).  
Version: root `VERSION` file.

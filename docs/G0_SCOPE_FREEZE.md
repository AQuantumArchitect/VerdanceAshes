# G0 — Scope freeze (Playtest demo)

**One-liner (store):** *A procedural campaign shell for Beyond All Reason: aces, a war map, and sorties that feed the story.*

## Demo is this

| Pillar | Playtest freeze |
|---|---|
| **Content spine** | 3 arcs × ~5 sorties (or 1-arc 5-mission if time-critical) on live seven-map pool; Mode A same-map chains preferred |
| **Dependency** | BAR must be installed; shell detects / uses design-forge path; **does not ship BAR** |
| **CYOA** | Graph-legal contracts; HTML war-map hub + C&C deploy board (capture / deploy / extract marks) |
| **FE v1** | **Vane + Ketha** aces: XP / rank / wounds; one bond channel; talk + rest choices |
| **Density room** | Graph qubits + local ρ matrix on focused theater (story pressure, not a second RTS) |
| **Combat** | Existing Verdance mutator + zone minimap; hub stamps seed then launches BAR |
| **Customer path** | `app\bin\PLAY.bat` → kernel launch (Phase 1); BAR bridge auto-apply (Phase 2); Steam stubs (Phase 3); see `docs/SHIP_ARCHITECTURE.md` |

## Demo is **not** this (until post-playtest)

- Shipping BAR engine inside Steam depot  
- Multiplayer  
- Live LLM online for core loop  
- Full MechWarrior mechlab (G9)  
- Full Null Mercs loadout bay (G8)  
- Full FE support-rank web for every NPC  
- Embedding BAR inside Chromium  
- **Full cognifold implementation** (BAR×SpaceWheat×hero molecules, live bridge, hub panel) — wishlist in `docs/UMWELT_GYM_PATHWAY.md` (thin hero umwelt molecules may ship earlier; full face is post-playtest)  

## Arc capture caps (C&C board)

| Arc | Missions | Max capture marks |
|---|---|---|
| 1 First Scar | 1–5 | 1 |
| 2 Second Scar | 6–10 | 2 |
| 3 Third Scar | 11–15 | 3 |

## Glue contract (shipped in forge)

```
hub deploy_plan.v1
  → tools/stamp_deploy_plan_v1.py
  → outbox/next_sortie_order.json
  → story engine intent
  → build_next_mission seed (captureZoneIds + hubChoiceId)
  → play_session / BAR
  → minimap paints primary + secondary captures
```

Open hub with BAR glue: `app\bin\HUB_HOST.bat` → http://127.0.0.1:8770/

## Exit criteria (G0 locked)

1. Friend can name the war **and** the aces after 10 minutes on hub.  
2. Commit on board stamps a real seed when host is up; offline still demos CYOA.  
3. Bay / garage remain honest locked stubs, not fake scope.

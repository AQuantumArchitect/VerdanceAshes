# Phase 1 systems revamp — shipped 2026-07-25

Operator play rants → Phase 1 of systems revamp plan.

## Shipped

| WO | Change |
|---|---|
| **WO-030** | `arcProfile` on every mission seed (`raid_tactics` / `contested_front` / `strike_lead`) |
| **WO-032** | 0 player commanders for tactics + Arc A/B; tactics kit (no `legcom`); gadget sweeps free engine coms |
| **WO-034** | `static_bases`: no enemy production labs; gadget **sweeps all enemy free commanders** |
| **WO-035** | Escalation mode from arc: Arc A off (hot extract only); Arc B light; Arc C full |
| **WO-038** | Null Merc kit scales by `allyPower` (M1 shred → M5 thin support) |
| **WO-031** | Plain-English **mission card** (WHERE / OBJECTIVE / HOW TO WIN / HOW IT ENDS / THREATS / ALLIES) |
| **WO-040** | HUD **TIME m:ss** + **PHASE FIGHT/EXTRACT** |

## Current seed (rebuild)

- Mission **va_005** Koom seize_lane  
- Arc: `contested_front` · playerCommanders **0** · enemyMode **static_bases** · allyPower **0.25** · escalation **light**  
- Heroes: Vane + Ketha still in kit  

## Infolog greps (verify)

- `VA_BRIDGE_LOADED ... playerComs=0`
- `VA_SWEEP_PLAYER_COMMANDERS`
- `VA_SWEEP_ENEMY_COMMANDERS`
- Mission card at start (paused); top HUD shows `TIME` + `PHASE`

## Not yet (Phase 2+)

- Unit printer (WO-033)
- Adjacent-only contracts (WO-039)
- Minimap zones (WO-041)
- Debrief next-mission picker (WO-042)
- Full in-engine Reload loop (WO-043+)

## Play

`C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\PLAY_SESSION_V1.bat`

# WO-004 — Ten-Minute Sortie Shape

**Date:** 2026-07-24  
**Status:** BUILT (compile-time + gadget cadence knobs)  
**Headless 9–11 min measure:** deferred (operator said build-first)

---

## What changed

### Compiler (`scripts/build_next_mission_v1.ps1`)

1. **Clock:** contracts / `targetDuration=10min` → `requiredFrames = 19800` (~11 min soft).
2. **Front-band deploy:** contract missions slide player start 45% toward the target zone center so first contact is not a corner march.
3. **Thinner static garrison:** presence camps use `FrontBand` patrol/perimeter; fortify rings skipped on front-band.
4. **Pack cadence knobs** written into `missionBase.escalation`:
   - `firstWaveFrame = 2700` (~90s)
   - `intervalFrames = 1800` (~60s)
   - `maxWaves = 8` (~9 min of mid-sortie packs)
   - gadget already spawns waves when not profiling

### Intent

- `environment.targetDuration = "10min"` on contract materialize.

### Design beat (unchanged intent)

| Time | Beat |
|---|---|
| 0:00–1:30 | Land near from↔target border |
| 1:30–5:00 | Packs every ~60s |
| 5:00–8:00 | Hold scar / objective window |
| 8:00–10:00 | Extract to far LZ |

---

## Acceptance

| Criterion | Status |
|---|---|
| Pack cadence knobs in seed | YES |
| No full base wipe required (presence) | YES (already) |
| Headless lands 9–11 min at diff 3 | NOT RUN — live play is acceptance |

---

## Paths

| Item | Path | Len |
|---|---|---|
| Compiler | `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\scripts\build_next_mission_v1.ps1` | 85 |
| Scenario | `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\data\scenarios\generated\next_mission_intent.playable.json` | 113 |
| Report | `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\outbound\WO-004_REPORT.md` | 87 |
